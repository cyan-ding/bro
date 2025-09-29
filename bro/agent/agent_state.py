"""
Agent State Management for Bro

This module provides centralized state management for the Bro agent, tracking context
that should be included in LLM calls including file operations,
open tabs, and other relevant information that persists across iterations.

@file purpose: Manages persistent agent state for context in LLM calls
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from patchright.async_api import Page
from utils.action_utils import generate_action_description


@dataclass
class Extraction:
    """
    Represents extracted content from a web page.
    
    Tracks the content, source information, and metadata of content
    that has been extracted during the session.
    """
    content: str
    source_url: str
    source_title: str
    content_length: int


@dataclass 
class TabState:
    """
    Represents the state of an open browser tab/page.
    
    Tracks open tabs, including duplicates of the same URL, in the same
    order as the browser context. The index corresponds to the tab's
    position within the browser's tab strip (
    0-based index matching context.pages order).
    """
    url: str
    title: str
    is_active: bool = False




@dataclass
class TodoItem:
    """
    Represents a single todo item in the agent's todo list.
    """
    task: str
    completed: bool = False


@dataclass
class StructuredOutputContext:
    """
    Represents structured output from LLM responses.

    Tracks thinking, evaluation of previous goals, memory, and next goals
    from the LLM's structured JSON responses.
    """
    thinking: str
    evaluation_previous_actions: str
    memory: str
    next_goal: str

@dataclass
class ActionContext:
    """
    Represents context from previous actions taken by the agent.
    """
    action_name: str
    arguments: Dict[str, Any]
    result: str
    iteration: int
    description: Optional[str] = None  # Human-readable description of the action
    structured_output: Optional[StructuredOutputContext] = None  # Associated structured output


class AgentState:
    """
    Centralized state management for the Bro agent.
    
    This class maintains all context that should be included in LLM calls,
    including file states, browser tabs, and action history.
    The state is designed to be serializable and provides formatted output
    for inclusion in LLM prompts.
    """
    
    def __init__(self, user_id: str = "default", session_id: str = "default"):
        """
        Initialize the agent state.

        Args:
            user_id: User identifier for session tracking
            session_id: Session identifier for session tracking
        """
        self.user_id = user_id
        self.session_id = session_id
        self.extractions: List[Extraction] = []
        self.tabs: List[TabState] = []
        self.action_history: List[ActionContext] = []
        self.todo_list: List[TodoItem] = []
        self.max_action_history = 100
        self.max_extractions = 50  # Limit number of extractions to keep

        # Track session metadata
        self.current_tab_index: Optional[int] = None
        
    def add_extraction(
        self, 
        content: str,
        source_url: str,
        source_title: str,
    ) -> None:
        """
        Add extracted content to the state.
        
        Args:
            content: The extracted content
            source_url: URL of the source page
            source_title: Title of the source page
        """
        
        extraction = Extraction(
            content=content,
            source_url=source_url,
            source_title=source_title,
            content_length=len(content),
        )
        
        self.extractions.append(extraction)
        
        # Keep only the most recent extractions
        if len(self.extractions) > self.max_extractions:
            self.extractions = self.extractions[-self.max_extractions:]
    
    
    def add_tab_state(self, url: str, title: str, is_active: bool = False) -> None:
        """
        Append a browser tab state to the ordered list. Allows duplicates.
        
        Args:
            url: URL of the tab
            title: Title of the tab
            is_active: Whether this is the currently active tab
        """
        # If marking active, first clear active flags
        if is_active:
            for tab in self.tabs:
                tab.is_active = False
        
        self.tabs.append(TabState(url=url, title=title, is_active=is_active))
        
        # Update current tab tracking
        if is_active:
            self.current_tab_index = len(self.tabs) - 1
    
    async def update_tab_state(self, page: Page) -> None:
        """
        Assuming that the page variable in @agent is the active page, update agent tab state.
        """

        context = page.context
        pages = context.pages

        try:
            # Compare the number of browser pages with the number of tracked tabs
            if len(pages) > len(self.tabs):
                # Find the index where new tabs start
                start_idx = len(self.tabs)
                for i in range(start_idx, len(pages)):
                    new_url = pages[i].url
                    new_title = await pages[i].title()
                    # Add the new tab as inactive for now
                    self.tabs.append(TabState(url=new_url, title=new_title, is_active=False))
                    self.set_current_tab_index(len(self.tabs) - 1)

            # if no new tabs/agent just switched tabs, that should be covered in the search tool already
        except Exception as e:
            print(f"⚠️ Failed to update page state: {e}")


    def update_todo_list(self, todo_items: List[Dict[str, Any]]) -> str:
        """
        Update the entire todo list with a structured list of todo items.

        Args:
            todo_items: List of dictionaries with 'task' and 'completed' keys

        Returns:
            Success message with todo count
        """
        # Clear existing todo list
        self.todo_list.clear()

        # Convert dictionaries to TodoItem objects
        for item_dict in todo_items:
            if 'task' in item_dict:
                task = item_dict['task']
                completed = item_dict.get('completed', False)
                self.todo_list.append(TodoItem(task=task, completed=completed))

        completed_count = sum(1 for item in self.todo_list if item.completed)
        return f"Todo list updated with {len(self.todo_list)} items ({completed_count} completed)"

    
    def add_action_context(
        self,
        action_name: str,
        arguments: Dict[str, Any],
        result: str,
        iteration: int,
        description: Optional[str] = None,
        highlighted_elements: Optional[List[Dict[str, Any]]] = None,
        structured_output: Optional[StructuredOutputContext] = None,
        print_result: bool = True
    ) -> None:
        """
        Add action context to history and optionally print it.
        
        Args:
            action_name: Name of the action that was performed
            arguments: Arguments passed to the action
            result: Result of the action
            iteration: Iteration number when action was performed
            description: Optional human-readable description of the action
            highlighted_elements: Optional list of highlighted elements for detailed descriptions
            structured_output: Optional content about thinking, memory, etc. 
            print_result: Whether to print the action result to console
        """
        # Generate description if not provided
        if description is None:
            description = generate_action_description(action_name, arguments, highlighted_elements)
            
        action_context = ActionContext(
            action_name=action_name,
            arguments=arguments,
            result=result,
            iteration=iteration,
            description=description,
            structured_output=structured_output
        )
        
        self.action_history.append(action_context)
        
        # Print the action result if requested
        if print_result:
            action_str = f" | Action description: {description}" if description else f" | Action arguments: {arguments}"
            thinking_str = f" | Thinking: {structured_output.thinking}" if structured_output and structured_output.thinking else ""
            print(f"📊 [Iteration {iteration}] | {action_name}{action_str}{thinking_str} | {result}")
        
        # Keep only the most recent actions
        if len(self.action_history) > self.max_action_history:
            self.action_history = self.action_history[-self.max_action_history:]
    
    def get_context_for_llm(self) -> str:
        """
        Generate formatted context string for inclusion in LLM prompts.
        
        Args:
            include_full_files: Whether to include full file contents or just summaries
            
        Returns:
            Formatted context string ready for LLM consumption
        """
        context_parts = []
        
        # Session information
        context_parts.append("=== AGENT SESSION CONTEXT ===")        
        # Current page information
        if self.current_tab_index is not None and self.tabs:
            if 0 <= self.current_tab_index < len(self.tabs):
                current_tab = self.tabs[self.current_tab_index]
                context_parts.append(f"Current Page: {current_tab.title} ({current_tab.url[:30]}) [Tab {self.current_tab_index}]")
        
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
                context_parts.append(f"{i}. {extraction.source_title} ({extraction.source_url})")
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
            for i, action in enumerate(self.action_history[-10:]):  # Show last 10 actions to avoid overwhelming context
                if action.description:
                    # Use human-readable description if available
                    context_parts.append(f"- Iteration {action.iteration}: {action.description}")
                else:
                    # Fallback to technical format
                    args_str = ", ".join(f"{k}={v}" for k, v in list(action.arguments.items())[:2])  # Show first 2 args
                    if len(action.arguments) > 2:
                        args_str += "..."

                    result_preview = action.result[:100] + "..." if len(action.result) > 100 else action.result
                    context_parts.append(f"- Iteration {action.iteration}: {action.action_name}({args_str}) -> {result_preview}")

                # Include specifics of most recent structured output if available
                if i == len(self.action_history[-10:]) - 1 and action.structured_output:
                    context_parts.append(f"  Reasoning about previous goal: {action.structured_output.thinking}")
                    context_parts.append(f"  Evaluation of previous goal: {action.structured_output.evaluation_previous_actions}")
                    context_parts.append(f"  Memory: {action.structured_output.memory}")
                    context_parts.append(f"  Current Goal: {action.structured_output.next_goal}")

        
        context_parts.append("=== END AGENT CONTEXT ===\n")
        
        return "\n".join(context_parts)
    
    def get_tab_by_index(self, index: int) -> Optional[TabState]:
        """
        Get a tab by its zero-based index in the tabs list.
        
        Args:
            index: Zero-based index of the tab
            
        Returns:
            TabState object if index is valid, None otherwise
        """
        if 0 <= index < len(self.tabs):
            return self.tabs[index]
        return None
    
    
    def set_current_tab_index(self, index: int):
        """
        Set the current tab by index.
        
        Args:
            index: Zero-based index of the tab to set as current
            
        Returns:
            True if successful, False if index is invalid
        """
        if 0 <= index < len(self.tabs):
            # Mark all tabs as inactive
            for tab in self.tabs:
                tab.is_active = False
            # Mark the selected tab as active
            self.tabs[index].is_active = True
            self.current_tab_index = index
    
    def get_tabs_summary(self) -> Dict[str, Any]:
        """
        Get a summary of tracked tabs for debugging/monitoring.
        
        Returns:
            Dictionary with tab summary information
        """
        return {
            "total_tabs": len(self.tabs),
            "active_tab_index": self.current_tab_index,
            "tabs": [
                {"index": i, "url": tab.url, "title": tab.title, "active": tab.is_active}
                for i, tab in enumerate(self.tabs)
            ]
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
        
        Args:
            iteration: Optional iteration number to include in the saved data
            
        Returns:
            Path to the saved state file
        """
        import json
        from pathlib import Path
        session_dir = Path.home() / ".bro" / self.user_id / f"session-{self.session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Use consistent filename that gets updated instead of creating new files
        filename = "agent_state.json"
        state_file = session_dir / filename
        
        # Convert state to dictionary
        state_data = self.to_dict()
        
        # Save to file (overwrites existing file)
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)
            
        return str(state_file)
    
    def to_dict(self) -> Dict[str, Any]:
        from datetime import datetime
        """
        Convert state to dictionary for serialization.
        
        Returns:
            Dictionary representation of the agent state
        """
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "last_edited": datetime.now().isoformat(),
            "current_tab_index": self.current_tab_index,
            "extractions": [
                {
                    "content": e.content,
                    "source_url": e.source_url,
                    "source_title": e.source_title,
                    "content_length": e.content_length,
                }
                for e in self.extractions
            ],
            "tabs": [
                {"index": i, "url": t.url, "title": t.title, "is_active": t.is_active}
                for i, t in enumerate(self.tabs)
            ],
            "todo_list": [
                {
                    "task": todo.task,
                    "completed": todo.completed
                }
                for todo in self.todo_list
            ],
            "action_history": [
                {
                    "action_name": a.action_name,
                    "arguments": a.arguments,
                    "result": a.result,
                    "iteration": a.iteration,
                    "description": a.description,
                    "structured_output": {
                        "thinking": a.structured_output.thinking,
                        "evaluation_previous_actions": a.structured_output.evaluation_previous_actions,
                        "memory": a.structured_output.memory,
                        "next_goal": a.structured_output.next_goal,
                    } if a.structured_output else None
                }
                for a in self.action_history
            ],
        }


# Global state manager instance - will be initialized by agent
_agent_state: Optional[AgentState] = None


def initialize_agent_state(user_id: str = "default", session_id: str = "default") -> AgentState:
    """
    Initialize the global agent state manager.
    
    Args:
        user_id: User identifier for session-based file management
        session_id: Session identifier for session-based file management
        
    Returns:
        Initialized AgentState instance
    """
    global _agent_state
    _agent_state = AgentState(user_id=user_id, session_id=session_id)
    return _agent_state


def get_agent_state() -> Optional[AgentState]:
    """
    Get the current agent state manager.
    
    Returns:
        Current AgentState instance or None if not initialized
    """
    return _agent_state


def clear_agent_state() -> None:
    """
    Clear the global agent state (useful for testing or cleanup).
    """
    global _agent_state
    if _agent_state:
        _agent_state.clear_state()
    _agent_state = None
