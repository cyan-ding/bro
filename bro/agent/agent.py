import asyncio
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bro.utils.use_cdp import use_cdp
from patchright.async_api import Page, async_playwright
from pydantic import BaseModel
from dotenv import load_dotenv

from .build_llm_prompt import build_llm_prompt
from .schemas import StructuredOutput

# Import utility functions
from bro.utils.action_utils import format_elements_text
from .actions import click, done, extract, input_text, scroll, search, todo_edit
from .agent_state import initialize_agent_state
from .ai import ai
from bro.utils.dom_utils import take_screenshot_with_bounding_boxes
from bro.utils.input_manager import InputManager

if TYPE_CHECKING:
    from api.run_info import RunInfo


# Clean Pydantic models for LiteLLM response handling
class LiteLLMFunction(BaseModel):
    name: Optional[str] = None
    arguments: Optional[str] = None


class LiteLLMToolCall(BaseModel):
    type: str
    function: LiteLLMFunction
    id: Optional[str] = None

    class Config:
        extra = "allow"  # Allow extra fields


class LiteLLMMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[LiteLLMToolCall]] = None
    thinking_content: Optional[str] = None

    class Config:
        extra = "allow"  # Allow extra fields


class LiteLLMChoice(BaseModel):
    message: LiteLLMMessage
    index: Optional[int] = None
    finish_reason: Optional[str] = None

    class Config:
        extra = "allow"  # Allow extra fields


class LiteLLMResponse(BaseModel):
    choices: List[LiteLLMChoice]
    model: Optional[str] = None
    id: Optional[str] = None

    class Config:
        extra = "allow"  # Allow extra fields


class Agent:
    """
    Bro agent that autonomously interacts with web pages using LLM guidance.

    The agent runs a loop that:
    1. Takes a screenshot with bounding boxes and element indices
    2. Calls the LLM with the screenshot and element information
    3. Parses the LLM response for tool calls using element indices
    4. Maps indices to XPath selectors and executes the tool call
    5. Repeats until task completion

    The agent uses element indices for targeting.
    """

    def __init__(
        self,
        system_prompt: str,
        session_id: str = str(uuid.uuid4())[:8],
        user_id: Optional[str] = None,
        model: str = "gpt-5-mini-2025-08-07",
        run_info: Optional["RunInfo"] = None,
    ):
        """
        Initialize the Bro agent.

        Args:
            system_prompt: The system prompt that defines Bro's behavior
            session_id: Unique identifier for this session
            user_id: Unique identifier for the user
            model: The model to use for the LLM
            run_info: Optional RunInfo object for logging
        """
        self.system_prompt = system_prompt
        self.session_id = session_id
        self.user_id = user_id or "default"
        self.model = model
        self.input_manager = None
        self.run_info = run_info
        # Initialize agent state with session info
        self.agent_state = initialize_agent_state(
            user_id=self.user_id, session_id=self.session_id
        )
        load_dotenv()
        print(
            f"🔧 Initialized agent state (user: {self.user_id}, session: {self.session_id})"
        )

    async def _parse_structured_json(
        self, llm_response: Any
    ) -> Optional[Dict[str, Any]]:
        """Parse the model's structured JSON content into actions and meta fields.

        Expects content to be a JSON object with keys: thinking, evaluation_previous_actions,
        memory, next_goal, action (array of single-key objects like {"click": {...}}).

        Returns a dict with keys: thinking, evaluation_previous_actions, memory, next_goal,
        actions (normalized list of {name, arguments}).
        """
        if not llm_response:
            return None
        try:
            # Normalize to dict
            if hasattr(llm_response, "model_dump"):
                response_dict = llm_response.model_dump()
            elif hasattr(llm_response, "dict"):
                response_dict = llm_response.dict()
            else:
                response_dict = llm_response
            response = LiteLLMResponse.model_validate(response_dict)

            try:
                content = response.choices[0].message.content
            except (AttributeError, IndexError) as e:
                print(f"Error accessing message content: {e}")
                return None

            if not content:
                print("No content in LLM response")
                return None

            try:
                obj = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON content: {e}")
                return None

            # Validate on structured output
            validated = StructuredOutput.model_validate(obj)
            normalized_actions: List[Dict[str, Any]] = []
            for action in validated.actions:
                normalized_actions.append(
                    {
                        "name": action.action_name,
                        "arguments": action.arguments.model_dump()
                        if hasattr(action.arguments, "model_dump")
                        else action.arguments,
                    }
                )
            return {
                "thinking": validated.thinking,
                "evaluation_previous_actions": validated.evaluation_previous_actions,
                "memory": validated.memory,
                "next_goal": validated.next_goal,
                "actions": normalized_actions,
            }
        except Exception as e:
            print(f"Error parsing structured JSON: {e}")
            return None

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
                        print("📄 Extracting content from page")

                        result = await extract(
                            page,
                            agent_state=self.agent_state,
                        )
                        success_msg = "Successfully extracted content from page"
                        print(f"✅ {success_msg}")
                        results.append(result)

                    case "todo_edit":
                        todo_items = arguments.get("todo_items", [])
                        print(f"📝 Updating todo list with {len(todo_items)} items")

                        result = await todo_edit(todo_items, self.agent_state)
                        print(f"✅ {result}")
                        results.append(result)

                    case "done":
                        reason = arguments.get("reason")
                        if not reason:
                            error_msg = "Error: reason is required for done"
                            print(f"❌ {error_msg}")
                            results.append(error_msg)
                            continue
                        print(f"🏁 Agent believes task is complete: {reason}")
                        result = await done(reason)
                        results.append(result)
                        print(f"✅ {result}")

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

    async def _handle_user_decision(
        self, reason: str, input_manager: Optional[InputManager] = None
    ) -> Tuple[str, str]:
        """
        Handle user decision when the agent signals completion.

        Args:
            reason: The reason the agent believes the task is complete
            input_manager: Optional InputManager for queue-based input

        Returns:
            Tuple of (decision, user_input) where decision is 'done', 'modify', or 'intervene'
        """
        print("\n" + "=" * 80)
        print("🤖 AGENT COMPLETION NOTIFICATION")
        print("=" * 80)
        print(f"The agent believes the task is complete: {reason}")
        print("\nWhat would you like to do?")
        print("  ✅ [D] DONE - Accept completion and exit")
        print("  🔄 [M] MODIFY - Provide additional instructions to continue")
        print("  🛠️  [I] INTERVENE - Allow manual intervention then continue")
        print("=" * 80)

        while True:
            try:
                # Use input_manager if available, otherwise fall back to direct input
                if input_manager:
                    choice = await input_manager.get_decision()
                    choice = choice.strip().upper()
                else:
                    choice = input("\nEnter your choice (D/M/I): ").strip().upper()

                if choice in ["D", "DONE"]:
                    return "done", ""
                elif choice in ["M", "MODIFY"]:
                    print("\n📝 Please provide additional instructions for the agent:")
                    if input_manager:
                        user_input = await input_manager.get_decision()
                        user_input = user_input.strip()
                    else:
                        user_input = input("> ").strip()

                    if user_input:
                        return "modify", user_input
                    else:
                        print("❌ Please provide some instructions.")
                        continue
                elif choice in ["I", "INTERVENE"]:
                    print("\n🛠️  MANUAL INTERVENTION MODE")
                    print(
                        "The browser will remain open for you to make manual changes."
                    )
                    print(
                        "Press ENTER when you're done with manual changes to continue automation..."
                    )
                    if input_manager:
                        await input_manager.get_decision()
                    else:
                        input()
                    return "intervene", ""
                else:
                    print("❌ Invalid choice. Please enter D, M, or I.")
                    continue

            except KeyboardInterrupt:
                print("\n\n🛑 Exiting on user request...")
                return "done", ""
            except EOFError:
                print("\n\n🛑 EOF detected, exiting...")
                return "done", ""

    async def run(
        self,
        user_prompt: str,
        url: str = "",
        max_iterations: int = 10,
        take_screenshot: bool = False,
        enable_input_queue: bool = True,
    ) -> None:
        """
        Run the agent loop to complete the user's task.

        Args:
            user_prompt: The user's task description
            url: The URL to navigate to (optional)
            max_iterations: Maximum number of iterations to prevent infinite loops
            take_screenshot: Whether to take screenshots during execution
            enable_input_queue: Whether to enable the input queue for real-time user messages

        Returns:
            None (action results are tracked in agent state and printed to console)
        """
        print("Starting browser context...")

        # Initialize input manager if enabled
        # Disable stdin listener since we're running via API (uses queues directly)
        if enable_input_queue:
            self.input_manager = InputManager(enable_stdin=False)
            await self.input_manager.start()

        async with async_playwright() as p:
            # browser_context = await p.chromium.launch_persistent_context(
            #     user_data_dir="./browser_data",
            #     channel="chrome",
            #     headless=False,
            #     no_viewport=True,
            # )
            await use_cdp()
            self.browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            # List contexts (Chrome profiles)
            contexts = self.browser.contexts
            if contexts:
                browser_context = contexts[0]  # Use existing profile
            else:
                browser_context = await self.browser.new_context()  # Or create new
            # Open a new tab
            page = (
                browser_context.pages[0]
                if browser_context.pages
                else await browser_context.new_page()
            )
            # Install DOM change detector early so it persists across navigations
            # page = await browser_context.new_page()

            # If no URL provided, navigate to blank page to start
            if not url:
                print("No initial URL provided, starting with blank page...")
                await page.goto("about:blank")
            else:
                await page.goto(url, wait_until="load")

            start_iteration = 0

            try:
                print("Starting agentic cycle...")
                last_signature: Optional[str] = None

                for iteration in range(start_iteration, max_iterations):
                    # check if current tab index is not the page we are on, if so, switch to it
                    if browser_context.pages:
                        if (
                            self.agent_state.current_tab_index is not None
                            and 0
                            <= self.agent_state.current_tab_index
                            < len(browser_context.pages)
                        ):
                            page = browser_context.pages[
                                self.agent_state.current_tab_index
                            ]
                        else:
                            page = browser_context.pages[0]

                    # Require a DOM change before proceeding to next iteration
                    # Take screenshot and get element information (optionally wait for change)
                    should_wait_for_change = False
                    # Check if the last action was one that likely causes DOM changes
                    if self.agent_state.action_history:
                        last_action = self.agent_state.action_history[-1]
                        should_wait_for_change = last_action.action_name in (
                            "click",
                            "input_text",
                            "search",
                        )

                    page_data = None
                    try:
                        page_data = await take_screenshot_with_bounding_boxes(
                            page,
                            wait_for_change=should_wait_for_change,
                            previous_signature=last_signature,
                            take_screenshot=take_screenshot,
                        )
                    except Exception as e:
                        # Add screenshot error to agent state so agent can react
                        error_msg = f"Failed to take screenshot: {str(e)}. You may need to navigate to a website first using the search tool."
                        print(f"⚠️ Screenshot error: {error_msg}")
                        await self.agent_state.add_action_context(
                            action_name="screenshot_error",
                            arguments={},
                            result=error_msg,
                            iteration=iteration,
                            print_result=True,
                        )

                    if not page_data:
                        # Continue to LLM call without screenshot data
                        viewport_info = {
                            "pixelsAbove": 0,
                            "pixelsBelow": 0,
                            "documentHeight": 0,
                            "innerHeight": 0,
                        }
                        elements_text = "No page loaded - you may need to use the search tool to navigate to a website."
                        screenshot_text = ""
                    else:
                        viewport_info = page_data["viewport_info"]
                        # Update signature for next iteration change detection
                        last_signature = page_data.get("signature")

                        # Format the user prompt with current page information
                        elements_text = await format_elements_text(
                            page_data["highlighted_elements"]
                        )
                        # print("Elements text: ", elements_text)

                        screenshot_text = (
                            "A screenshot has been attached showing the current page with bounding boxes around interactive elements. "
                            "Each box has an index number that corresponds to the elements listed above. "
                            if page_data.get("screenshot")
                            else ""
                        )

                    agent_context = self.agent_state.get_context_for_llm()

                    # Check for new user messages from the input queue
                    user_messages = []
                    if self.input_manager:
                        user_messages = self.input_manager.get_messages()

                    # Append user messages to the prompt if any
                    user_interrupt_text = ""
                    if user_messages:
                        interrupt_messages = "\n".join(
                            [f"- {msg}" for msg in user_messages]
                        )
                        user_interrupt_text = f"\n\nUSER INTERRUPTS (New instructions from user):\n{interrupt_messages}\n"
                        print(f"💬 Received {len(user_messages)} user message(s)")

                    enhanced_prompt = f"""
                            User prompt:
							{user_prompt}
							{user_interrupt_text}

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
                    params = build_llm_prompt(
                        user_prompt=enhanced_prompt,
                        system_prompt=self.system_prompt,
                        model=self.model,
                        screenshot=page_data.get("screenshot") if page_data else None,
                    )

                    llm_response = await ai(params)

                    parsed = await self._parse_structured_json(llm_response)

                    if not parsed or not parsed.get("actions"):
                        print(f"⚠️  Iteration {iteration}: No actions returned by LLM")
                        print(parsed)
                        # Add no actions result to agent state
                        await self.agent_state.add_action_context(
                            action_name="no_actions",
                            arguments={},
                            result="ERROR: LLM did not return actions - task may be complete, or response invalid",
                            iteration=iteration,
                            print_result=True,
                        )
                        break

                    tool_calls = parsed["actions"]
                    print(
                        f"🔄 Iteration {iteration}: Executing {len(tool_calls)} action(s)"
                    )
                    # Execute the tool calls
                    result_messages = await self._execute_tool_call(
                        tool_calls,
                        page,
                        page_data.get("highlighted_elements", []) if page_data else [],
                    )

                    # Create structured output context for action history
                    structured_output_context = None
                    if parsed and any(
                        parsed.get(field)
                        for field in [
                            "thinking",
                            "evaluation_previous_actions",
                            "memory",
                            "next_goal",
                        ]
                    ):
                        from .agent_state import StructuredOutputContext

                        structured_output_context = StructuredOutputContext(
                            thinking=parsed.get("thinking", ""),
                            evaluation_previous_actions=parsed.get(
                                "evaluation_previous_actions", ""
                            ),
                            memory=parsed.get("memory", ""),
                            next_goal=parsed.get("next_goal", ""),
                        )

                    # Add each tool call to agent state context with structured output
                    for i, tool_call in enumerate(tool_calls):
                        result_message = (
                            result_messages[i]
                            if i < len(result_messages)
                            else "No result"
                        )
                        # Add action to agent state context with structured output
                        await self.agent_state.add_action_context(
                            action_name=tool_call["name"],
                            arguments=tool_call["arguments"],
                            result=result_message,
                            iteration=iteration,
                            highlighted_elements=page_data.get(
                                "highlighted_elements", []
                            )
                            if page_data
                            else [],
                            structured_output=structured_output_context,
                            logger=self.run_info.add_log_event,
                        )

                    # Agent state update at end of iteration
                    await self.agent_state.update_tab_state(page)

                    # Update iteration in run_info
                    if self.run_info:
                        self.run_info.update_iteration(
                            iteration,
                            tool_calls[0]["name"] if tool_calls else "no_action",
                        )

                    # Save agent state to file at end of iteration
                    try:
                        state_file = await self.agent_state.save_state_to_file()
                        print(f"💾 Agent state saved to: {state_file}")

                    except Exception as e:
                        print(f"⚠️ Failed to save agent state: {e}")

                    # Check if the agent signaled task completion via done function
                    await_decision_messages = [
                        msg
                        for msg in result_messages
                        if msg.startswith("AWAIT_USER_DECISION:")
                    ]
                    if await_decision_messages:
                        reason = await_decision_messages[0].replace(
                            "AWAIT_USER_DECISION: ", ""
                        )
                        decision, user_input = await self._handle_user_decision(
                            reason, self.input_manager
                        )

                        if decision == "done":
                            print(
                                "🛑 User accepted task completion, stopping execution."
                            )
                            break
                        elif decision == "modify":
                            # Add user's additional instructions to the original prompt
                            user_prompt = f"{user_prompt}\n\nADDITIONAL INSTRUCTIONS: {user_input}"
                            print(
                                f"🔄 Continuing with additional instructions: {user_input}"
                            )
                            # Continue with the loop - the new instructions will be included in the next iteration
                        elif decision == "intervene":
                            print("🛠️  Continuing after manual intervention...")
                            # Continue with the loop - user made manual changes

                    print("=" * 100)
            finally:
                print("Exiting browser...")
                await browser_context.close()
                if self.input_manager:
                    await self.input_manager.stop()

    async def close_connection(self) -> None:
        """
        Close the browser connection (CDP connection only, does not kill Chrome process).
        """
        if self.browser:
            await self.browser.close()
            print("✅ Browser connection closed")
            if self.input_manager:
                await self.input_manager.stop()


async def main():
    # Load the Bro system prompt
    system_prompt = Path("bro.txt").read_text(encoding="utf-8")
    prompts = [
        "Log in to linkedin and report back on what three people have posted.",
        "Open gmail and send an email to blueplus.d@gmail.com with the subject 'Hello' and the body 'This is a test email'",
        """Find three different research papers on AI on arxiv and collect the full text info (not just the abstract).
        Afterwards, output an essay about the material you collected. 
         """,
    ]
    agent = Agent(
        system_prompt,
        session_id="test",
        user_id="cyan",
        model="gemini/gemini-2.5-flash-preview-09-2025",
    )
    # claude-sonnet-4-20250514
    # gemini/gemini-2.5-flash-preview-09-2025
    # groq/llama-4-scout-17b-16e-instruct
    await agent.run(
        user_prompt=prompts[0],
        # url="https://arxiv.org/list/cs.AI/recent",
        max_iterations=100,
        take_screenshot=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
