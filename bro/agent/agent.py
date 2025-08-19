"""
Agent class for Bro - autonomous web interaction agent

This module provides the Agent class that runs a loop making LLM calls and executing
tool calls to complete web interaction tasks. It handles screenshots, bounding boxes,
element indexing, and tool call parsing according to OpenAI documentation. The agent
uses element indices for targeting and automatically maps them to XPath selectors.

@file purpose: Provides the main agent loop for Bro web interaction
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from browser.use_cdp import use_cdp
from patchright.async_api import Page, async_playwright
from pydantic import BaseModel, Field

from prompts.tools.gpt.gpt_actions import gpt_actions

# Import utility functions
from .action_utils import format_elements_text, get_previous_action_description
from .actions import (
    click,
    done,
    input_text,
    # extract,  # Commented out - will implement later
    scroll,
    search,
)
from .ai import gpt
from .credentials import get_credentials
from .dom_utils import take_screenshot_with_bounding_boxes


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
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the dataclass to a dictionary for backward compatibility."""
        result_dict = {
            "iteration": self.iteration,  # iteration number to limit token use
            "action": self.action,  # name of tool call
            "result": self.result,  # result of tool call
        }
        if self.arguments is not None:
            result_dict["arguments"] = self.arguments  # arguments of tool call
        if self.reasoning is not None:
            result_dict["reasoning"] = self.reasoning
        return result_dict

    def __str__(self) -> str:
        """Return a formatted string representation for real-time visibility."""
        status = "✅ SUCCESS" if not self.result.startswith("Error") else "❌ ERROR"
        args_str = f" | Args: {self.arguments}" if self.arguments else ""
        reason_str = f" | Reasoning: {self.reasoning}" if self.reasoning else ""
        return f"[Iteration {self.iteration}] {status} | {self.action}{args_str}{reason_str} | {self.result}"


class OutputTextBlock(BaseModel):
    type: Optional[str] = None
    text: Optional[str] = None


class SummaryTextBlock(BaseModel):
    type: Optional[str] = None
    text: Optional[str] = None


class OutputItem(BaseModel):
    # For assistant message blocks
    type: Optional[str] = None
    id: Optional[str] = None
    status: Optional[str] = None
    role: Optional[str] = None
    content: Optional[List[OutputTextBlock]] = None
    # For function call blocks
    name: Optional[str] = None
    arguments: Optional[str] = None
    # For reasoning blocks
    summary: Optional[List[SummaryTextBlock]] = None


class OpenAIResponse(BaseModel):
    output: List[OutputItem] = Field(default_factory=list)


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

    async def _extract_reasoning_from_llm_response(
        self, llm_response: Dict[str, Any]
    ) -> Optional[str]:
        """
        Extract reasoning summary from either assistant message or reasoning block.
        """
        if not llm_response:
            return None

        try:
            parsed = OpenAIResponse.model_validate(llm_response, from_attributes=True)
        except Exception:
            return None

        if not parsed.output:
            return None

        # Prefer explicit reasoning summary if present
        for item in parsed.output:
            if item.type == "reasoning" and item.summary:
                texts: List[str] = [
                    s.text for s in item.summary if s and isinstance(s.text, str)
                ]
                if texts:
                    combined = "\n".join(texts)
                    return combined.strip()
        return None

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
        3. Navigate to the website using the search tool

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
        reasoning = await self._extract_reasoning_from_llm_response(llm_response)

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
            "reasoning": reasoning,
        }

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
        try:
            parsed = OpenAIResponse.model_validate(llm_response, from_attributes=True)
        except Exception as e:
            print(f"Error validating OpenAI response: {e}")
            return []

        for item in parsed.output:
            if item.type == "function_call" and item.name and item.arguments:
                try:
                    args_obj = json.loads(item.arguments)
                except json.JSONDecodeError as e:
                    print(f"Error parsing function_call arguments JSON: {e}")
                    continue
                tool_calls.append({"name": item.name, "arguments": args_obj})

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

        def _find_element_by_index(target_idx: int) -> Optional[Dict[str, Any]]:
            """Return element dict matching the stable 'index' field, or None if not found."""
            for el in highlighted_elements:
                if isinstance(el, dict) and el.get("index") == target_idx:
                    return el
            # Fallback: if list position matches, try direct index access
            if 0 <= target_idx < len(highlighted_elements):
                return highlighted_elements[target_idx]
            return None

        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            arguments = tool_call.get("arguments")

            print(f"🔧 Executing tool: {tool_name} with arguments: {arguments}")

            try:
                match tool_name:
                    case "click":
                        target_index = arguments.get("target")

                        if target_index is None:
                            error_msg = "Error: target is required for click"
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue

                        element = _find_element_by_index(target_index)
                        if element is None:
                            error_msg = f"Error: Invalid target index {target_index} (no matching element)"
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue

                        target_xpath = element["xpath"]
                        iframe_xpath = element.get("iframe_xpath")
                        print(
                            f"🎯 Clicking element at index {target_index} with xpath: {target_xpath}"
                        )

                        await click(page, target_xpath, iframe_xpath)
                        success_msg = (
                            f"Successfully clicked on element at index {target_index}"
                        )
                        print(f"✅ {success_msg}")
                        results.append(success_msg)

                    case "input_text":
                        target_index = arguments.get("target")
                        input_text_value = arguments.get("input_text")
                        placeholder = arguments.get("login")
                        retry_login = bool(arguments.get("retry_login", False))

                        if target_index is None:
                            error_msg = "Error: target is required for text_input"
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue

                        element = _find_element_by_index(target_index)
                        if element is None:
                            error_msg = f"Error: Invalid target index {target_index} (no matching element)"
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue

                        # Handle login credentials if provided
                        if placeholder:
                            print(
                                f"🔐 Looking up credentials for placeholder: {placeholder}"
                            )
                            credentials = await get_credentials(
                                placeholder, retry_login=retry_login
                            )
                            if credentials:
                                input_text_value = credentials
                                print(f"🔐 Found credentials for {placeholder}")
                            else:
                                # If missing and retry requested, get_credentials already prompted and may have updated file
                                # When still None, we just report that credential is unavailable and allow agent to continue.
                                msg = f"Credential '{placeholder}' is unavailable."
                                print(msg)
                                results.append(msg)
                                continue

                        if not input_text_value:
                            error_msg = "Error: input_text is required for text_input"
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue

                        target_xpath = element["xpath"]
                        iframe_xpath = element.get("iframe_xpath")
                        print(
                            f"📝 Entering text '{input_text_value}' into element at index {target_index} with xpath: {target_xpath}"
                        )
                        await input_text(
                            page, target_xpath, input_text_value, iframe_xpath
                        )
                        success_msg = f"Successfully entered text '{input_text_value}' into element at index {target_index}"
                        print(f"✅ {success_msg}")
                        results.append(success_msg)

                    case "scroll":
                        how_much = arguments.get("how_much")
                        if how_much is None:
                            error_msg = "Error: how_much is required for scroll"
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue
                        print(f"📜 Scrolling by {how_much} pixels")
                        await scroll(page, how_much)
                        success_msg = f"Successfully scrolled by {how_much} pixels"
                        print(f"✅ {success_msg}")
                        results.append(success_msg)

                    case "search":
                        query = arguments.get("query")
                        if not query:
                            error_msg = "Error: query is required for search"
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue
                        print(f"🔍 Searching for: {query}")
                        await search(page, query)
                        success_msg = f"Successfully searched for: {query}"
                        print(f"✅ {success_msg}")
                        results.append(success_msg)

                    case "done":
                        reason = arguments.get("reason")
                        if not reason:
                            error_msg = "Error: reason is required for done"
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue
                        print(f"🏁 Task completed with reason: {reason}")
                        result = await done(reason)
                        results.append(result)
                        print(f"✅ {result}")
                        # Signal to stop the agent loop
                        results.append("STOP_AGENT")
                        print("🛑 Agent signaled task completion")

                    case _:
                        error_msg = f"Unknown tool: {tool_name}"
                        print(f"❌ {error_msg}")
                        results.append(error_msg)

            except Exception as e:
                error_msg = f"Error executing {tool_name}: {str(e)}"
                print(f"💥 EXCEPTION: {error_msg}")
                print(f"💥 Exception type: {type(e).__name__}")
                import traceback

                print(f"💥 Traceback: {traceback.format_exc()}")
                results.append(error_msg)

        return results

    async def run(
        self,
        user_prompt: str,
        url: str = "",
        max_iterations: int = 10,
        screenshot: bool = False,
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
        await use_cdp()
        async with async_playwright() as p:
            # browser_context = await p.chromium.launch_persistent_context(
            #     user_data_dir="./browser_data",
            #     channel="chrome",
            #     headless=False,
            #     no_viewport=True,
            # )
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            # List contexts (Chrome profiles)
            contexts = browser.contexts
            if contexts:
                browser_context = contexts[0]  # Use existing profile
            else:
                browser_context = await browser.new_context()  # Or create new
            print(browser_context.pages[0].url)
            # Open a new tab
            page = (
                browser_context.pages[0]
                if browser_context.pages
                else await browser_context.new_page()
            )
            # Install DOM change detector early so it persists across navigations
            # page = await browser_context.new_page()

            # If no URL provided, use the start function to initialize the process
            if not url:
                print("No initial URL provided, running start function...")
                start_result = await self._start(user_prompt)

                if start_result["status"] == "error":
                    error_result = ActionResult(
                        iteration=0,
                        action="start",
                        result=start_result["result"],
                    )
                    print(f"❌ {error_result}")
                    return [error_result]

                # Execute the initial tool call from start function
                initial_tool_call = start_result["tool_call"]
                print(f"🚀 Executing initial tool call: {initial_tool_call['name']}")
                result_messages = await self._execute_tool_call(
                    [initial_tool_call], page, []
                )

                # Initialize results list
                results = []

                # Create ActionResult object for the initial tool call
                initial_result = ActionResult(
                    iteration=0,
                    action=initial_tool_call["name"],
                    arguments=initial_tool_call["arguments"],
                    result=result_messages[0] if result_messages else "No result",
                    reasoning=start_result.get("reasoning"),
                )
                print(f"📊 {initial_result}")
                results.append(initial_result)

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
                previous_elements = None
                last_signature: Optional[str] = None
                for iteration in range(start_iteration, max_iterations):
                    # Require a DOM change before proceeding to next iteration
                    # Take screenshot and get element information (optionally wait for change)
                    should_wait_for_change = False
                    if previous_action and isinstance(previous_action, dict):
                        action_name = previous_action.get("name")
                        # Wait for change primarily after actions that likely cause SPA updates
                        should_wait_for_change = action_name in (
                            "click",
                            "input_text",
                            "search",
                        )

                    page_data = await take_screenshot_with_bounding_boxes(
                        page,
                        wait_for_change=should_wait_for_change,
                        previous_signature=last_signature,
                        take_screenshot=screenshot,
                    )

                    if not page_data:
                        raise RuntimeError(
                            "Invalid page: unable to take screenshot or analyze DOM. Please check the URL and try again."
                        )

                    viewport_info = page_data["viewport_info"]
                    # Update signature for next iteration change detection
                    last_signature = page_data.get("signature")

                    # Format the user prompt with current page information
                    elements_text = await format_elements_text(
                        page_data["highlighted_elements"]
                    )
                    print("Elements text: ", elements_text)
                    # Read current todo list
                    # todo_list = await self._read_todo_list()

                    # Add previous action information to the prompt
                    previous_action_text = ""
                    if previous_action and previous_elements:
                        if isinstance(previous_action, dict):
                            previous_action_text = get_previous_action_description(
                                previous_action, previous_elements
                            )
                        else:
                            previous_action_text = f"\nPrevious action: You executed '{previous_action}' in the last iteration. Please follow up on this action to continue with the task."
                    screenshot_text = (
                        "A screenshot has been attached showing the current page with bounding boxes around interactive elements. "
                        "Each box has an index number that corresponds to the elements listed above. "
                        if page_data.get("screenshot")
                        else ""
                    )
                    enhanced_prompt = f"""
                            User prompt: 
							{user_prompt}

							Current page information:
							{elements_text}

							Viewport position: 
							There are {viewport_info["pixelsAbove"]} pixels above your current view and {viewport_info["pixelsBelow"]} pixels below.
							The page is {viewport_info["documentHeight"]} pixels tall and your viewport is {viewport_info["innerHeight"]} pixels tall.

							{screenshot_text}

							{previous_action_text}

							Please choose the next action to take to complete the task.
							"""
                    print(f"Sending LLM Query {iteration}...")
                    # Call the LLM
                    params = gpt_actions(
                        user_prompt=enhanced_prompt,
                        system_prompt=self.system_prompt,
                        model="gpt-5-mini-2025-08-07",
                        screenshot=page_data["screenshot"],
                    )

                    llm_response = await gpt(params)

                    reasoning = await self._extract_reasoning_from_llm_response(
                        llm_response
                    )
                    if not reasoning:
                        print("LLM response: ", llm_response)
                    print(f"Reasoning: {reasoning}")
                    # Parse for tool calls
                    tool_calls = await self._parse_tool_call(llm_response)

                    if not tool_calls:
                        print(f"⚠️  Iteration {iteration}: No tool calls made by LLM")
                        no_tool_result = ActionResult(
                            iteration=iteration,
                            action="no_tool_call",
                            result="ERROR: LLM did not make a tool call - task may be complete, or tool call failed",
                            reasoning=reasoning,
                        )
                        print(f"📊 {no_tool_result}")
                        results.append(no_tool_result)
                        break

                    print(
                        f"🔄 Iteration {iteration}: Executing {len(tool_calls)} tool call(s)"
                    )
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
                        action_result = ActionResult(
                            iteration=iteration,
                            action=tool_call["name"],
                            arguments=tool_call["arguments"],
                            result=result_message,
                            reasoning=reasoning if iteration == 0 else None,
                        )
                        print(f"📊 {action_result}")
                        results.append(action_result)
                        # Update previous action for next iteration
                        previous_action = {
                            "name": tool_call["name"],
                            "arguments": tool_call["arguments"],
                        }
                        previous_elements = page_data["highlighted_elements"]

                    # Check if the agent signaled task completion via done function
                    if "STOP_AGENT" in result_messages:
                        print("🛑 Agent signaled task completion, stopping execution.")
                        break

                return results

            finally:
                print("Exiting browser...")
                await browser_context.close()


async def main():
    # Load the Bro system prompt
    system_prompt = Path("prompts/bro.txt").read_text(encoding="utf-8")
    prompts = [
        "Open a new google doc and write an essay about cherries",
        "Open gmail and send an email to blueplus.d@gmail.com with the subject 'Hello' and the body 'This is a test email'",
    ]
    # Create and run the agent
    agent = Agent(system_prompt)
    results = await agent.run(
        user_prompt=prompts[1],
        # "https://accounts.google.com/v3/signin/identifier?checkedDomains=youtube&continue=https%3A%2F%2Faccounts.google.com%2F&flowEntry=ServiceLogin&flowName=GlifWebSignIn&followup=https%3A%2F%2Faccounts.google.com%2F&ifkv=AdBytiOYvUAqRJUi6-iHJ04pgCOhk2j6OcoLbvaXOx0XwJgfuW3iXQLuT72oPUhYKHIGRfbxqqxE&pstMsg=1&dsh=S757206094%3A1754856863191091",
        max_iterations=20,
        screenshot=True,
    )

    # Print results
    for result in results:
        print(f"Iteration {result.iteration}: {result.action} - {result.result}")


if __name__ == "__main__":
    asyncio.run(main())
