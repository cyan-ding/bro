"""
Agent class for Bro - autonomous web interaction agent

This module provides the Agent class that runs a loop making LLM calls and executing
tool calls to complete web interaction tasks. It handles screenshots, bounding boxes,
element indexing, and tool call parsing according to OpenAI documentation. The agent
uses element indices for targeting and automatically maps them to XPath selectors.

@file purpose: Provides the main agent loop for Bro web interaction
"""

import asyncio
import base64
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from actions import (
    click,
    done,
    input_text,
    # extract,  # Commented out - will implement later
    scroll,
    search,
)
from ai import gpt
from patchright.async_api import Page, async_playwright

from prompts.tools.gpt import gpt_actions


@dataclass
class ActionResult:
    """
    Standardized result structure for agent actions.

    Represents the result of a single action taken by the Bro agent,
    including both successful tool executions and error conditions.
    """

    iteration: int
    action: str
    result: str
    arguments: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the dataclass to a dictionary for backward compatibility."""
        result_dict = {
            "iteration": self.iteration,  # iteration number to limit token use
            "action": self.action,  # name of tool call
            "result": self.result,  # result of tool call
        }
        if self.arguments is not None:
            result_dict["arguments"] = self.arguments  # arguments of tool call
        return result_dict


class Agent:
    """
    Bro agent that autonomously interacts with web pages using LLM guidance.

    The agent runs a loop that:
    1. Takes a screenshot with bounding boxes and element indices
    2. Calls the LLM with the screenshot and element information
    3. Parses the LLM response for tool calls using element indices
    4. Maps indices to XPath selectors and executes the tool call
    5. Repeats until task completion

    The agent uses element indices for targeting and automatically handles credential
    lookup for login functionality.
    """

    def __init__(self, system_prompt: str):
        """
        Initialize the Bro agent.

        Args:
            system_prompt: The system prompt that defines Bro's behavior
        """
        self.system_prompt = system_prompt
        self.session_id = str(uuid.uuid4())[:8]  # Short session ID
        self.todo_file = f"todo_{self.session_id}.md"

    async def _read_todo_list(self) -> str:
        """
        Read the current todo list from the session-specific markdown file.

        Returns:
            The content of the todo list file, or empty string if file doesn't exist
        """
        from pathlib import Path

        todo_path = Path(self.todo_file)
        try:
            if todo_path.exists():
                return todo_path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError) as e:
            print(f"Error reading todo list: {e}")
        return ""

    async def _write_todo_list(self, content: str) -> None:
        """
        Write content to the session-specific todo list markdown file.

        Args:
            content: The content to write to the todo list
        """
        from pathlib import Path

        todo_path = Path(self.todo_file)
        try:
            todo_path.write_text(content, encoding="utf-8")
        except (PermissionError, OSError) as e:
            print(f"Error writing todo list: {e}")

    async def _initialize_todo_list(self, user_prompt: str) -> None:
        """
        Initialize the todo list with tasks based on the user prompt.

        Args:
            user_prompt: The user's task description
        """
        initial_todo = f"""# Todo List - Session {self.session_id}

        ## Task: {user_prompt}

        ### Subtasks to Complete:
        - [ ] Subtask 1
        - [ ] Subtask 2

        ### Notes:
        - Started at: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        - Status: In Progress

        """
        await self._write_todo_list(initial_todo)

    async def _start(self, user_prompt: str) -> Dict[str, Any]:
        """
        Initialize the process when there are no webpages to take screenshots of yet.
        This function focuses only on populating the todo list with a detailed breakdown
        of the user's task, ensuring the first item is a search action.

        Args:
            user_prompt: The user's task description

        Returns:
            Dictionary containing the result of the initial setup
        """
        print("Starting initial setup...")

        # Initialize the todo list
        # await self._initialize_todo_list(user_prompt)

        # Create initial prompt for the LLM to plan the task
        initial_prompt = f"""
        User task: {user_prompt}

        You are starting a new web automation task. Your job is to:
        1. Break down the user's task into specific subtasks
        2. Identify the first website to visit
        3. NAVIGATE TO THE WEBSITE FIRST using the search tool

        CRITICAL INSTRUCTIONS:
        - You MUST call the search tool to navigate to the first website
        - This is the ONLY way to start navigating to websites
        - The search tool is your primary navigation method
        """

        print("Making initial LLM call for task planning...")

        # Call the LLM without a screenshot since we don't have a webpage yet
        params = gpt_actions(
            user_prompt=initial_prompt,
            system_prompt=self.system_prompt,
            model="gpt-5-nano-2025-08-07",
            screenshot=None,  # No screenshot available yet
        )

        llm_response = await gpt(params)

        # Parse for tool calls
        tool_calls = await self._parse_tool_call(llm_response)

        if not tool_calls:
            return {
                "status": "error",
                "result": "LLM did not make a tool call during initial setup. Initial setup failed",
            }

        # For the start function, we'll return the first tool call to be executed by the main run loop
        return {
            "status": "success",
            "tool_call": tool_calls[0],  # Take the first tool call
            "result": "Initial setup completed, tool call ready for execution",
        }

    async def _load_js_bundle(self) -> str:
        """Load and bundle the JavaScript code for DOM analysis with caching."""
        base_path = Path(__file__).parent / "dom"
        cache_file = base_path / "js_bundle_cache.txt"
        files_in_order = [
            "metrics.js",
            "highlight.js",
            "dom_utils.js",
            "buildDomTree.js",
        ]

        # Check if cache exists and use it
        if cache_file.exists():
            try:
                cached_bundle = cache_file.read_text(encoding="utf-8")
                return cached_bundle
            except (OSError, IOError) as e:
                print(f"Error reading cache file: {e}")
                # Continue to rebuild if cache read fails

        # Rebuild the bundle
        import re

        full_code = []
        for file_name in files_in_order:
            file_path = base_path / file_name
            try:
                code = file_path.read_text(encoding="utf-8")
                # Remove import/export statements
                code = re.sub(r"^\s*import .*from .*", "", code, flags=re.MULTILINE)
                code = re.sub(r"^\s*export (default )?", "", code, flags=re.MULTILINE)
                full_code.append(code)
            except (FileNotFoundError, PermissionError) as e:
                print(f"Error loading JavaScript file {file_name}: {e}")
                raise RuntimeError(
                    f"Failed to load required JavaScript file: {file_name}"
                )

        # Wrap in an IIFE to expose the main function
        bundle = f"""
		(() => {{
			{"".join(full_code)}
			window.buildDomTree = buildDomTree;
		}})();
		"""

        # Cache the bundle
        try:
            cache_file.write_text(bundle, encoding="utf-8")
        except (OSError, IOError) as e:
            print(f"Warning: Could not write cache file: {e}")

        return bundle

    async def _take_screenshot_with_bounding_boxes(
        self, page: Page
    ) -> Optional[Dict[str, Any]]:
        """
        Take a screenshot and analyze the DOM to get bounding boxes and element information.

        Args:
            page: The Playwright page object

        Returns:
            Dictionary containing screenshot data and highlighted elements
        """
        if page.url == "about:blank":
            return None
        print("Walking DOM Tree...")
        # Load the JavaScript bundle
        js_bundle = await self._load_js_bundle()
        await page.evaluate(js_bundle)

        # Call buildDomTree to get element information and highlighting
        result = await page.evaluate(
            "(args) => window.buildDomTree(args)",
            {
                "doHighlightElements": True,
                "debugMode": False,
                "overlapThreshold": 0.4,
                "indexByPosition": True,
            },
        )

        # Get viewport information for smart scrolling
        viewport_info = await page.evaluate("""
			() => {
				const scrollY = window.scrollY;
				const innerHeight = window.innerHeight;
				const documentHeight = document.documentElement.scrollHeight;
				return {
					innerHeight: innerHeight,
					documentHeight: documentHeight,
					pixelsAbove: scrollY,
					pixelsBelow: documentHeight - (scrollY + innerHeight)
				};
			}
		""")
        print("Highlighted elements: ", result.get("highlightedElements", []))
        # Take screenshot
        screenshot_bytes = await page.screenshot()
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        return {
            "screenshot": screenshot_base64,
            "highlighted_elements": result.get("highlightedElements", []),
            "viewport_info": viewport_info,
        }

    async def _format_elements_text(self, highlighted_elements: List[Dict]) -> str:
        """
        Format the highlighted elements into readable text for the LLM.

        Args:
            highlighted_elements: List of highlighted element data

        Returns:
            Formatted text describing all interactive elements
        """
        if not highlighted_elements:
            return "No interactive elements found on the page."
        print("Formatting elements...")
        elements_text = "Interactive elements on the page:\n\n"
        for i, element in enumerate(highlighted_elements):
            elements_text += f"Index {i}: {element.get('tag', 'unknown')}"
            if element.get("info", {}).get("textContent"):
                elements_text += f" - '{element['info']['textContent']}'"
            if element.get("info", {}).get("href"):
                elements_text += f" (href: {element['info']['href']})"
            if element.get("info", {}).get("placeholder"):
                elements_text += f" (placeholder: {element['info']['placeholder']})"
            elements_text += "\n"

        return elements_text

    async def _get_credentials(self, placeholder: str) -> Optional[str]:
        """
        Get credentials from the credentials file based on placeholder.

        Args:
            placeholder: The placeholder string (e.g., 'GOOGLE_EMAIL', 'GOOGLE_PASSWORD')

        Returns:
            The credential value if found, None otherwise
        """
        print("Retrieving credentials...")
        credentials_file = Path("credentials.txt")
        if not credentials_file.exists():
            print(
                "No credentials detected, generating file. Please fill in credentials before proceeding."
            )
            credentials_file.write_text(
                "# Sample credentials file for Bro\n"
                "# Format: PLACEHOLDER=actual_value\n"
                "# \n"
            )
            value = input(f"Enter value for {placeholder}: ").strip()
            if value:
                with open(credentials_file, "a", encoding="utf-8") as f:
                    f.write(f"{placeholder}={value}\n")
                return value
            return None

        credentials = {}
        try:
            with open(credentials_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line:
                        key, value = line.split("=", 1)
                        credentials[key.strip()] = value.strip()
        except (FileNotFoundError, PermissionError) as e:
            print(f"Error reading credentials file: {e}")
            return None

        # Use fuzzy matching to locate the closest key in credentials for the given placeholder
        import difflib

        if placeholder in credentials:
            return credentials[placeholder]
        # Find the closest match using difflib
        matches = difflib.get_close_matches(
            placeholder, credentials.keys(), n=1, cutoff=0.6
        )
        if matches:
            return credentials[matches[0]]
        return None

    async def _parse_tool_call(
        self, llm_response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Parse the LLM response for multiple tool calls according to OpenAI documentation.

        Args:
            llm_response: The response from the LLM

        Returns:
            List of tool call data if found, empty list otherwise
        """
        print("Parsing tool calls...")
        if not llm_response:
            return []

        tool_calls = []
        # Find all function calls
        for item in llm_response.output:
            if item.type == "function_call":
                function_call = item
                try:
                    function_call_arguments = json.loads(function_call.arguments)
                    tool_calls.append(
                        {
                            "name": function_call.name,
                            "arguments": function_call_arguments,
                        }
                    )
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Error parsing function call: {e}")
                    continue

        return tool_calls

    async def _execute_tool_call(
        self,
        tool_calls: List[Dict[str, Any]],
        page: Page,
        highlighted_elements: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Execute multiple tool calls using the appropriate action functions.

        Args:
            tool_calls: List of tool call data to execute
            page: The Playwright page object
            highlighted_elements: List of highlighted element data for mapping indices to xpaths

        Returns:
            List of result messages from the tool executions
        """
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            arguments = tool_call.get("arguments")

            print(f"Executing tool: {tool_name}")

            try:
                match tool_name:
                    case "click":
                        target_index = arguments.get("target")

                        if target_index is None:
                            results.append("Error: target is required for click")
                            continue

                        if target_index >= len(highlighted_elements):
                            results.append(
                                f"Error: Invalid target index {target_index}"
                            )
                            continue

                        target_xpath = highlighted_elements[target_index]["xpath"]
                        await click(page, target_xpath)
                        results.append(
                            f"Successfully clicked on element at index {target_index}"
                        )

                    case "input_text":
                        target_index = arguments.get("target")
                        input_text_value = arguments.get("input_text")
                        placeholder = arguments.get("login")

                        if target_index is None:
                            results.append("Error: target is required for text_input")
                            continue

                        if target_index >= len(highlighted_elements):
                            results.append(
                                f"Error: Invalid target index {target_index}"
                            )
                            continue

                        # Handle login credentials if provided
                        if placeholder:
                            credentials = await self._get_credentials(placeholder)
                            if credentials:
                                input_text_value = credentials

                        if not input_text_value:
                            results.append(
                                "Error: input_text is required for text_input"
                            )
                            continue

                        target_xpath = highlighted_elements[target_index]["xpath"]
                        await input_text(page, target_xpath, input_text_value)
                        results.append(
                            f"Successfully entered text '{input_text_value}' into element at index {target_index}"
                        )

                    case "scroll":
                        how_much = arguments.get("how_much")
                        if how_much is None:
                            results.append("Error: how_much is required for scroll")
                            continue
                        await scroll(page, how_much)
                        results.append(f"Successfully scrolled by {how_much} pixels")

                    case "search":
                        query = arguments.get("query")
                        if not query:
                            results.append("Error: query is required for search")
                            continue
                        await search(page, query)
                        results.append(f"Successfully searched for: {query}")

                    case "done":
                        reason = arguments.get("reason")
                        if not reason:
                            results.append("Error: reason is required for done")
                            continue
                        result = await done(reason)
                        results.append(result)
                        # Signal to stop the agent loop
                        results.append("STOP_AGENT")

                    case _:
                        results.append(f"Unknown tool: {tool_name}")

            except Exception as e:
                results.append(f"Error executing {tool_name}: {str(e)}")

        return results

    async def run(
        self, user_prompt: str, url: str = "", max_iterations: int = 10
    ) -> List[ActionResult]:
        """
        Run the agent loop to complete the user's task.

        Args:
            user_prompt: The user's task description
            url: The URL to navigate to (optional)
            max_iterations: Maximum number of iterations to prevent infinite loops

        Returns:
            List of ActionResult objects from the agent's execution
        """
        print("Starting browser context...")
        async with async_playwright() as p:
            browser_context = await p.chromium.launch_persistent_context(
                user_data_dir="./browser_data",
                channel="chrome",
                headless=False,
                no_viewport=True,
            )

            page = await browser_context.new_page()

            # If no URL provided, use the start function to initialize the process
            if not url:
                print("No initial URL provided, running start function...")
                start_result = await self._start(user_prompt)

                if start_result["status"] == "error":
                    return [
                        ActionResult(
                            iteration=0,
                            action="start",
                            result=start_result["result"],
                        )
                    ]

                # Execute the initial tool call from start function
                initial_tool_call = start_result["tool_call"]
                result_messages = await self._execute_tool_call(
                    [initial_tool_call], page, []
                )

                # Initialize results list
                results = []

                # Create ActionResult object for the initial tool call
                results.append(
                    ActionResult(
                        iteration=0,
                        action=initial_tool_call["name"],
                        arguments=initial_tool_call["arguments"],
                        result=result_messages[0] if result_messages else "No result",
                    )
                )

                # Set the previous action for the main loop
                previous_action = {
                    "name": initial_tool_call["name"],
                    "arguments": initial_tool_call["arguments"],
                }

                # Continue with the main loop starting from iteration 1
                start_iteration = 1
            else:
                await page.goto(url, wait_until="load")
                results = []
                start_iteration = 0

            try:
                # if url:  # Only initialize todo list if we have a URL (start function handles it otherwise)
                #     print("Initializing todo list... ")
                #     await self._initialize_todo_list(user_prompt)

                print("Starting agentic cycle...")
                previous_action = None
                for iteration in range(start_iteration, max_iterations):
                    # Take screenshot and get element information
                    page_data = await self._take_screenshot_with_bounding_boxes(page)

                    if not page_data:
                        raise RuntimeError(
                            "Invalid page: unable to take screenshot or analyze DOM. Please check the URL and try again."
                        )
                    # Format the user prompt with current page information
                    elements_text = await self._format_elements_text(
                        page_data["highlighted_elements"]
                    )
                    viewport_info = page_data["viewport_info"]

                    # Read current todo list
                    # todo_list = await self._read_todo_list()

                    # Add previous action information to the prompt
                    previous_action_text = ""
                    if previous_action:
                        if isinstance(previous_action, dict):
                            action_name = previous_action.get("name", "unknown")
                            action_args = previous_action.get("arguments", {})
                            args_str = (
                                f" with arguments: {action_args}" if action_args else ""
                            )
                            previous_action_text = f"\nPrevious action: You executed '{action_name}{args_str}' in the last iteration. Please follow up on this action or continue with the task."
                        else:
                            previous_action_text = f"\nPrevious action: You executed '{previous_action}' in the last iteration. Please follow up on this action or continue with the task."

                    enhanced_prompt = f"""
                            User prompt: 
							{user_prompt}

							Current page information:
							{elements_text}

							Viewport position: 
							There are {viewport_info["pixelsAbove"]} pixels above your current view and {viewport_info["pixelsBelow"]} pixels below.
							The page is {viewport_info["documentHeight"]} pixels tall and your viewport is {viewport_info["innerHeight"]} pixels tall.

							The screenshot shows the current page with bounding boxes around interactive elements. 
							Each box has an index number that corresponds to the elements listed above. 

							{previous_action_text}

							Please choose the next action to take to complete the task.
							"""
                    print(f"Sending LLM Query {iteration}...")
                    # Call the LLM
                    params = gpt_actions(
                        user_prompt=enhanced_prompt,
                        system_prompt=self.system_prompt,
                        model="gpt-5-nano-2025-08-07",
                        screenshot=page_data["screenshot"],
                    )

                    llm_response = await gpt(params)

                    print("LLM Response: ", llm_response)
                    # Parse for tool calls
                    tool_calls = await self._parse_tool_call(llm_response)

                    if not tool_calls:
                        results.append(
                            ActionResult(
                                iteration=iteration,
                                action="no_tool_call",
                                result="LLM did not make a tool call - task may be complete, or tool call failed",
                            )
                        )
                        break

                    # Execute the tool calls
                    result_messages = await self._execute_tool_call(
                        tool_calls, page, page_data["highlighted_elements"]
                    )

                    # Create ActionResult objects for each tool call
                    for i, tool_call in enumerate(tool_calls):
                        result_message = (
                            result_messages[i]
                            if i < len(result_messages)
                            else "No result"
                        )
                        results.append(
                            ActionResult(
                                iteration=iteration,
                                action=tool_call["name"],
                                arguments=tool_call["arguments"],
                                result=result_message,
                            )
                        )
                        # Update previous action for next iteration
                        previous_action = {
                            "name": tool_call["name"],
                            "arguments": tool_call["arguments"],
                        }

                    # Check if the agent signaled task completion via done function
                    if "STOP_AGENT" in result_messages:
                        print("Agent signaled task completion, stopping execution.")
                        break

                    # Wait a moment for the page to update
                    await asyncio.sleep(1)

                return results

            finally:
                print("Exiting browser...")
                await browser_context.close()


async def main():
    # Load the Bro system prompt
    system_prompt = Path("prompts/roles/bro.txt").read_text(encoding="utf-8")

    # Create and run the agent
    agent = Agent(system_prompt)
    results = await agent.run("Log into my google account")

    # Print results
    for result in results:
        print(f"Iteration {result.iteration}: {result.action} - {result.result}")


if __name__ == "__main__":
    asyncio.run(main())
