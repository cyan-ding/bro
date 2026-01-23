from typing import Any, Awaitable, Callable, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from patchright.async_api import Page
from utils.action_utils import generate_action_description
from agent.models import (
    Extraction,
    TabState,
    TodoItem,
    ActionContext,
    StructuredOutputContext,
)


class AgentState(BaseModel):
    extractions: List[Extraction] = Field(default_factory=list)
    tabs: List[TabState] = Field(default_factory=list)
    action_history: List[ActionContext] = Field(default_factory=list)
    todo_list: List[TodoItem] = Field(default_factory=list)
    max_action_history: int = 100
    max_extractions: int = 50
    current_tab_index: Optional[int] = None
    last_edited: str = Field(default_factory=lambda: datetime.now().isoformat())
    max_iterations: int = 10

    def add_extraction(
        self,
        content: str,
        source_url: str,
        source_title: str,
    ) -> None:
        extraction = Extraction(
            content=content,
            source_url=source_url,
            source_title=source_title,
            content_length=len(content),
        )

        self.extractions.append(extraction)

        # Keep only the most recent extractions
        if len(self.extractions) > self.max_extractions:
            self.extractions = self.extractions[-self.max_extractions :]

    def add_tab_state(self, url: str, title: str, is_active: bool = False) -> None:
        # If marking active, first clear active flags
        if is_active:
            for tab in self.tabs:
                tab.is_active = False

        self.tabs.append(TabState(url=url, title=title, is_active=is_active))

        # Update current tab tracking
        if is_active:
            self.current_tab_index = len(self.tabs) - 1

    async def update_tab_state(
        self, page: Optional[Page] = None, update_url: Optional[str] = None
    ) -> None:
        """
        Assuming that the page variable in @agent is the active page, update agent tab state.
        In theory this should be able to take all current open URLs and update internal state based on that.
        """

        context = page.context
        pages = context.pages

        try:
            # Compare the number of browser pages with the number of tracked tabs
            if update_url:
                self.tabs[self.current_tab_index].url = update_url
            else:
                if len(pages) > len(self.tabs):
                    # Find the index where new tabs start
                    start_idx = len(self.tabs)
                    for i in range(start_idx, len(pages)):
                        new_url = pages[i].url
                        new_title = await pages[i].title()
                        # Add the new tab as inactive for now
                        self.tabs.append(
                            TabState(url=new_url, title=new_title, is_active=False)
                        )
                        self.set_current_tab_index(len(self.tabs) - 1)

            # if no new tabs/agent just switched tabs, that should be covered in the search tool already
        except Exception as e:
            print(f"⚠️ Failed to update page state: {e}")

    def update_todo_list(self, todo_items: List[Dict[str, Any]]) -> str:
        # Clear existing todo list
        self.todo_list.clear()

        # Convert dictionaries to TodoItem objects
        for item_dict in todo_items:
            if "task" in item_dict:
                task = item_dict["task"]
                completed = item_dict.get("completed", False)
                self.todo_list.append(TodoItem(task=task, completed=completed))

        completed_count = sum(1 for item in self.todo_list if item.completed)
        return f"Todo list updated with {len(self.todo_list)} items ({completed_count} completed)"

    async def add_action_context(
        self,
        action_name: str,
        arguments: Dict[str, Any],
        result: str,
        iteration: int,
        description: Optional[str] = None,
        highlighted_elements: Optional[List[Dict[str, Any]]] = None,
        structured_output: Optional[StructuredOutputContext] = None,
        print_result: bool = True,
        logger: Optional[Callable[[str, ActionContext], Awaitable[None]]] = None,
    ) -> None:
        # Generate description if not provided
        if description is None:
            description = generate_action_description(
                action_name, arguments, highlighted_elements
            )

        action_context = ActionContext(
            action_name=action_name,
            arguments=arguments,
            result=result,
            iteration=iteration,
            description=description,
            structured_output=structured_output,
        )

        # Call logger if provided, but strip structured_output from log (thinking is logged separately)
        if logger is not None:
            log_action_context = ActionContext(
                action_name=action_name,
                arguments=arguments,
                result=result,
                iteration=iteration,
                description=description,
                structured_output=None,
            )
            await logger("action", log_action_context)

        self.action_history.append(action_context)

        # Print the action result if requested
        if print_result:
            action_str = (
                f" | Action description: {description}"
                if description
                else f" | Action arguments: {arguments}"
            )
            thinking_str = (
                f" | Thinking: {structured_output.thinking}"
                if structured_output and structured_output.thinking
                else ""
            )
            print(
                f"📊 [Iteration {iteration}] | {action_name}{action_str}{thinking_str} | {result}"
            )

        # Keep only the most recent actions
        if len(self.action_history) > self.max_action_history:
            self.action_history = self.action_history[-self.max_action_history :]

    def get_context_for_llm(self) -> str:
        context_parts = []

        # Session information
        context_parts.append("=== AGENT SESSION CONTEXT ===")
        # Current page information
        if self.current_tab_index is not None and self.tabs:
            if 0 <= self.current_tab_index < len(self.tabs):
                current_tab = self.tabs[self.current_tab_index]
                context_parts.append(
                    f"Current Page: {current_tab.title} ({current_tab.url[:30]}) [Tab {self.current_tab_index}]"
                )

        # Browser tabs state
        if self.tabs:
            context_parts.append("\n=== OPEN BROWSER TABS ===")
            for i, tab in enumerate(self.tabs):
                status = "ACTIVE" if tab.is_active else "background"
                context_parts.append(f"[{i}] [{status}] {tab.title} ({tab.url[:30]})")

        # Extracted content by agent
        if self.extractions:
            context_parts.append("\n=== EXTRACTED CONTENT ===")
            for i, extraction in enumerate(self.extractions):
                context_parts.append(
                    f"{i}. {extraction.source_title} ({extraction.source_url})"
                )
                context_parts.append(f"   Length: {extraction.content_length} chars")
                context_parts.append(f"   Content:\n{extraction.content}")
                context_parts.append("")  # Empty line between extractions

        # Todo list
        if self.todo_list:
            context_parts.append("\n=== TODO LIST ===")
            for i, todo in enumerate(self.todo_list, 1):
                status = "[x]" if todo.completed else "[ ]"
                context_parts.append(f"{i}. {status} {todo.task}")

        # Action history with structured output
        if self.action_history:
            context_parts.append("\n=== PAST ACTIONS ===")
            for i, action in enumerate(
                self.action_history[-10:]
            ):  # Show last 10 actions to avoid overwhelming context
                if action.description:
                    # Use human-readable description if available
                    context_parts.append(
                        f"- Iteration {action.iteration}: {action.description}"
                    )
                else:
                    # Fallback to technical format
                    args_str = ", ".join(
                        f"{k}={v}" for k, v in list(action.arguments.items())[:2]
                    )  # Show first 2 args
                    if len(action.arguments) > 2:
                        args_str += "..."

                    result_preview = (
                        action.result[:100] + "..."
                        if len(action.result) > 100
                        else action.result
                    )
                    context_parts.append(
                        f"- Iteration {action.iteration}: {action.action_name}({args_str}) -> {result_preview}"
                    )

                # Include specifics of most recent structured output if available
                if i == len(self.action_history[-10:]) - 1 and action.structured_output:
                    context_parts.append(
                        f"  Reasoning about previous goal: {action.structured_output.thinking}"
                    )
                    context_parts.append(
                        f"  Evaluation of previous goal: {action.structured_output.evaluation_previous_actions}"
                    )
                    context_parts.append(f"  Memory: {action.structured_output.memory}")
                    context_parts.append(
                        f"  Current Goal: {action.structured_output.next_goal}"
                    )

        context_parts.append("=== END AGENT CONTEXT ===\n")

        return "\n".join(context_parts)

    def get_tab_by_index(self, index: int) -> Optional[TabState]:
        if 0 <= index < len(self.tabs):
            return self.tabs[index]
        return None

    def set_current_tab_index(self, index: int):
        if 0 <= index < len(self.tabs):
            # Mark all tabs as inactive
            for tab in self.tabs:
                tab.is_active = False
            # Mark the selected tab as active
            self.tabs[index].is_active = True
            self.current_tab_index = index

    def get_tabs_summary(self) -> Dict[str, Any]:
        return {
            "total_tabs": len(self.tabs),
            "active_tab_index": self.current_tab_index,
            "tabs": [
                {
                    "index": i,
                    "url": tab.url,
                    "title": tab.title,
                    "active": tab.is_active,
                }
                for i, tab in enumerate(self.tabs)
            ],
        }

    def clear_state(self) -> None:
        """
        Clear all state (useful for testing or reset scenarios).
        """
        self.extractions.clear()
        self.tabs.clear()
        self.action_history.clear()
        self.todo_list.clear()
        self.current_tab_index = None

    async def save_state_to_file(self) -> str:
        """
        Save the current agent state to a JSON file in the session directory.
        Uses a consistent filename that gets updated on each save instead of creating new files.

        Returns:
            Path to the saved state file
        """
        import json
        from pathlib import Path

        # Update last_edited timestamp
        self.last_edited = datetime.now().isoformat()

        session_dir = Path.home() / ".bro"
        session_dir.mkdir(parents=True, exist_ok=True)

        # Use consistent filename that gets updated instead of creating new files
        filename = "agent_state.json"
        state_file = session_dir / filename

        # Convert state to dictionary using Pydantic's model_dump
        state_data = self.model_dump(mode="json")

        # Save to file (overwrites existing file)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)

        return str(state_file)
