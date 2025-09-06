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
from dotenv import load_dotenv

from .gpt_actions import gpt_actions

# Import utility functions
from .action_utils import format_elements_text
from .actions import click, done, extract, file_system, input_text, scroll, search, search_rag
from .agent_state import initialize_agent_state
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
        args_str = f" | Args: {self.arguments}" if self.arguments else ""
        reason_str = f" | Reasoning: {self.reasoning}" if self.reasoning else ""
        return f"[Iteration {self.iteration}] | {self.action}{args_str}{reason_str} | {self.result}"


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

    def __init__(
        self,
        system_prompt: str,
        enable_rag: bool = False,
        session_id: str = str(uuid.uuid4())[:8],
        user_id: Optional[str] = None,
        model: str = "gpt-4.1-mini-2025-04-14",
    ):
        """
        Initialize the Bro agent.

        Args:
            system_prompt: The system prompt that defines Bro's behavior
            enable_rag: Whether to enable RAG pipeline for content processing
            session_id: Unique identifier for this session (used in Pinecone namespace )
            user_id: Unique identifier for the user (used for Pinecone index naming)
            model: The model to use for the LLM
        """
        self.system_prompt = system_prompt
        self.session_id = session_id
        self.user_id = user_id or "default" 
        self.enable_rag = enable_rag
        self.rag_initialized = False
        self.model = model
        # Initialize agent state with session info
        self.agent_state = initialize_agent_state(user_id=self.user_id, session_id=self.session_id)
        load_dotenv()
        print(f"🔧 Initialized agent state (user: {self.user_id}, session: {self.session_id})")

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

    async def _initialize_rag_if_needed(self) -> bool:
        """
        Helper function to initialize RAG pipeline if enabled and not already initialized.
        Uses Pinecone cloud vector database.

        Returns:
            True if RAG is available (was already initialized or just initialized),
            False if RAG is disabled or initialization failed.
        """
        if not self.enable_rag:
            return False

        if self.rag_initialized:
            return True

        try:
            from .rag import initialize_rag_pipeline, clear_rag_namespace

            print("🔄 Initializing Pinecone RAG pipeline...")
            await initialize_rag_pipeline(
                index_name=f"bro-user-{self.user_id}",
                namespace=f"session-{self.session_id}",
                max_chunk_size=800,
                chunk_overlap=150,
                min_chunk_size=50,
            )
            
            # Clear namespace for testing purposes
            print("🧪 Clearing Pinecone namespace for testing...")
            await clear_rag_namespace()
            
            self.rag_initialized = True
            print("✅ RAG pipeline initialized successfully")
            return True

        except Exception as e:
            print(f"❌ Failed to initialize RAG pipeline: {e}")
            print(
                "💡 Make sure PINECONE_API_KEY and VOYAGE_API_KEY environment variables are set"
            )
            self.enable_rag = False
            return False

    async def _start(self, user_prompt: str) -> Dict[str, Any]:
        """
        Initialize the process when there are no webpages to take screenshots of yet.
        This function focuses on starting the task by calling the LLM to plan
        and execute the first action, typically a search.

        Args:
            user_prompt: The user's task description

        Returns:
            Dictionary containing the result of the initial setup
        """
        print("Starting initial setup...")

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
            model=self.model,
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
                            page,
                            target_xpath,
                            input_text_value,
                            iframe_xpath,
                            self.agent_state,
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
                        tab_index = arguments.get("tab_index")

                        if not query and tab_index is None:
                            error_msg = "Error: either query or tab_index is required for search"
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue

                        if tab_index is not None:
                            print(f"🔄 Switching to tab index: {tab_index}")
                        else:
                            print(f"🔍 Searching for: {query}")

                        await search(page, query or "", tab_index, self.agent_state)

                        if tab_index is not None:
                            success_msg = (
                                f"Successfully switched to tab index: {tab_index}"
                            )
                        else:
                            success_msg = f"Successfully searched for: {query}"
                        print(f"✅ {success_msg}")
                        results.append(success_msg)

                    case "extract":
                        use_rag = arguments.get("use_rag", False)
                        file_name = arguments.get(
                            "file_name"
                        )  # Optional file_name from LLM
                        description = arguments.get(
                            "description"
                        )  # Optional description from LLM
                        print(f"📄 Extracting content from page (RAG: {use_rag})")

                        result = await extract(
                            page,
                            use_rag=use_rag,
                            agent_state=self.agent_state,
                            file_name=file_name,
                            description=description,
                        )
                        success_msg = "Successfully extracted content from page"
                        print(f"✅ {success_msg}")
                        results.append(result)

                    case "file_system":
                        # Import the Pydantic model
                        from .actions import FileSystemArgs

                        try:
                            # Validate arguments using Pydantic model
                            fs_args = FileSystemArgs.model_validate(arguments)
                            print(f"📁 File system operation: {fs_args.action}")

                            result = await file_system(
                                args=fs_args, agent_state=self.agent_state
                            )
                            print("✅ File system operation completed")
                            results.append(result)

                        except Exception as e:
                            error_msg = (
                                f"Error: Invalid file_system arguments - {str(e)}"
                            )
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue

                    case "search_rag":
                        # Import the Pydantic model
                        from .actions import RAGSearchArgs

                        try:
                            # Validate arguments using Pydantic model
                            rag_args = RAGSearchArgs.model_validate(arguments)
                            print(f"🔍 RAG search: {rag_args.query}")

                            result = await search_rag(
                                args=rag_args, agent_state=self.agent_state
                            )
                            print("✅ RAG search completed")
                            results.append(result)

                        except Exception as e:
                            error_msg = (
                                f"Error: Invalid search_rag arguments - {str(e)}"
                            )
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue

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
        take_screenshot: bool = False,
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

        # Initialize RAG if enabled
        rag_available = await self._initialize_rag_if_needed()
        if self.enable_rag and not rag_available:
            print("⚠️ RAG was requested but initialization failed")

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

                # Add initial tool call to action history (no highlighted_elements available for initial call)
                self.agent_state.add_action_context(
                    action_name=initial_tool_call["name"],
                    arguments=initial_tool_call["arguments"],
                    result=result_messages[0] if result_messages else "No result",
                    iteration=0,
                )

                # Continue with the main loop starting from iteration 1
                start_iteration = 1
            else:
                await page.goto(url, wait_until="load")
                results = []
                start_iteration = 0

            try:
                print("Starting agentic cycle...")
                
                
                last_signature: Optional[str] = None
                
                for iteration in range(start_iteration, max_iterations):

                    # check if current tab index is not the page we are on, if so, switch to it
                    if browser_context.pages:
                        if (self.agent_state.current_tab_index is not None and 
                            0 <= self.agent_state.current_tab_index < len(browser_context.pages)):
                            page = browser_context.pages[self.agent_state.current_tab_index]
                        else:
                            page = browser_context.pages[0]

                    # Require a DOM change before proceeding to next iteration
                    # Take screenshot and get element information (optionally wait for change)
                    should_wait_for_change = False
                    # Check if the last action was one that likely causes DOM changes
                    if self.agent_state.action_history:
                        last_action = self.agent_state.action_history[-1]
                        print(last_action)
                        should_wait_for_change = last_action.action_name in (
                            "click",
                            "input_text", 
                            "search",
                        )

                    page_data = await take_screenshot_with_bounding_boxes(
                        page,
                        wait_for_change=should_wait_for_change,
                        previous_signature=last_signature,
                        take_screenshot=take_screenshot,
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
                    # print("Elements text: ", elements_text)

                    # Previous action information is now provided through agent_context (RECENT ACTIONS section)

                    screenshot_text = (
                        "A screenshot has been attached showing the current page with bounding boxes around interactive elements. "
                        "Each box has an index number that corresponds to the elements listed above. "
                        if page_data.get("screenshot")
                        else ""
                    )
                    # Get agent state context for LLM
                    agent_context = self.agent_state.get_context_for_llm(
                        include_full_files=True
                    )

                    enhanced_prompt = f"""
                            User prompt: 
							{user_prompt}

							{agent_context}

							Current page information:
							{elements_text}

							Viewport position: 
							There are {viewport_info["pixelsAbove"]} pixels above your current view and {viewport_info["pixelsBelow"]} pixels below.
							The page is {viewport_info["documentHeight"]} pixels tall and your viewport is {viewport_info["innerHeight"]} pixels tall.

							{screenshot_text}

							Please choose the next action to take to complete the task.
							"""
                    print(f"Sending LLM Query {iteration}...")
                    # Call the LLM
                    params = gpt_actions(
                        user_prompt=enhanced_prompt,
                        system_prompt=self.system_prompt,
                        model=self.model,
                        screenshot=page_data["screenshot"],
                    )

                    llm_response = await gpt(params)

                    reasoning = await self._extract_reasoning_from_llm_response(
                        llm_response
                    )
         
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

                        # Add action to agent state context
                        self.agent_state.add_action_context(
                            action_name=tool_call["name"],
                            arguments=tool_call["arguments"],
                            result=result_message,
                            iteration=iteration,
                            highlighted_elements=page_data["highlighted_elements"],
                        )

                    # Agent state update at end of iteration
                    await self.agent_state.update_tab_state(page)
                    
                    # Save agent state to file at end of iteration
                    try:
                        state_file = await self.agent_state.save_state_to_file(iteration)
                        print(f"💾 Agent state saved to: {state_file}")
                        
                        # Print file tree for debugging
                        if iteration % 5 == 0:  # Print tree every 5 iterations to avoid spam
                            tree_repr = self.agent_state.get_file_tree_representation()
                            print(f"📂 File tree:\n{tree_repr}")
                            
                    except Exception as e:
                        print(f"⚠️ Failed to save agent state: {e}")

                    # Check if the agent signaled task completion via done function
                    if "STOP_AGENT" in result_messages:
                        print("🛑 Agent signaled task completion, stopping execution.")
                        break

                    print("=" * 100)

                return results

            finally:
                print("Exiting browser...")
                await browser_context.close()

                # Cleanup RAG pipeline if it was initialized
                if self.rag_initialized:
                    try:
                        from .rag import cleanup_rag_pipeline

                        await cleanup_rag_pipeline()
                    except Exception as e:
                        print(f"⚠️ Error during RAG cleanup: {e}")


async def main():
    # Load the Bro system prompt
    system_prompt = Path("bro.txt").read_text(encoding="utf-8")
    prompts = [
        "Log in to google.",
        "Open gmail and send an email to blueplus.d@gmail.com with the subject 'Hello' and the body 'This is a test email'",
        """Find an article about attention is all you need on arxiv and use retrieval augmented generation to extract data. 
        After you extract the data, use the search_rag tool to retrieve the relevant chunks. 
        Then, go to google docs and write an essay about their architectures in google doc. That is your final output.
        Make sure to only extract contents in html format, not pdf or any other format. DO NOT DO THE SAME ACTION YOU JUST DID.
         """,
    ]
    # third one should test rag, files, todolist, tab switching,
    agent = Agent(system_prompt, enable_rag=True, session_id="test", user_id="cyan", model="gpt-5-2025-08-07")
    results = await agent.run(
        user_prompt=prompts[0],
        # url="https://arxiv.org/list/cs.AI/recent",
        max_iterations=100,
        take_screenshot=True,
    )

    # Print results
    for result in results:
        print(f"Iteration {result.iteration}: {result.action} - {result.result}")


if __name__ == "__main__":
    asyncio.run(main())
