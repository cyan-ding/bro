"""
Agent State Management for Bro

This module provides centralized state management for the Bro agent, tracking context
that should be included in LLM calls including file operations, RAG retrieval results,
open tabs, and other relevant information that persists across iterations.

@file purpose: Manages persistent agent state for context in LLM calls
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from patchright.async_api import Page
from .action_utils import get_element_description


def _generate_action_description(
    action_name: str, 
    arguments: Dict[str, Any], 
    highlighted_elements: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Generate a human-readable description of an action with optional element context.
    
    Args:
        action_name: Name of the action
        arguments: Arguments passed to the action
        highlighted_elements: Optional list of highlighted elements for detailed descriptions
        
    Returns:
        Human-readable description of the action
    """
    def _get_element_desc(index):
        """Helper to get element description with fallback."""
        if highlighted_elements and get_element_description:
            return get_element_description(index, highlighted_elements)
        return f"element at index {index}"
    
    if action_name == "click":
        target = arguments.get("target", "unknown")
        element_desc = _get_element_desc(target)
        return f"You clicked on {element_desc}"
    elif action_name == "input_text":
        target = arguments.get("target", "unknown")
        element_desc = _get_element_desc(target)
        text = arguments.get("input_text", "")
        login = arguments.get("login")
        if login:
            retry_login = arguments.get("retry_login", False)
            if retry_login:
                return f"You retried login with '{login}' into {element_desc}"
            else:
                return f"You entered login credentials '{login}' into {element_desc}"
        else:
            return f"You typed '{text}' into {element_desc}"
    elif action_name == "scroll":
        how_much = arguments.get("how_much", "")
        return f"You scrolled by {how_much} pixels"
    elif action_name == "search":
        query = arguments.get("query", "")
        tab_index = arguments.get("tab_index")
        if tab_index is not None:
            return f"You switched to tab {tab_index}"
        else:
            return f"You searched for '{query}'"
    elif action_name == "extract":
        use_rag = arguments.get("use_rag", False)
        file_name = arguments.get("file_name", "content")
        description = arguments.get("description", "")
        if use_rag:
            return f"You extracted content using RAG processing ('{description}')"
        else:
            return f"You extracted content and saved it to '{file_name}' ('{description}')"
    elif action_name == "file_system":
        action_type = arguments.get("action", "")
        filename = arguments.get("filename", "")
        if action_type == "read":
            return f"You read the file '{filename}'"
        elif action_type == "write":
            return f"You wrote content to file '{filename}'"
        elif action_type == "list_files":
            return "You listed files in the ~/.bro directory"
        else:
            return f"You performed file system action '{action_type}'"
    elif action_name == "search_rag":
        query = arguments.get("query", "")
        top_k = arguments.get("top_k", 5)
        return f"You searched the RAG database for '{query}' (top {top_k} results)"
    elif action_name == "done":
        reason = arguments.get("reason", "task completed")
        return f"You marked the task as done with reason: '{reason}'"
    else:
        return f"You executed '{action_name}'"


@dataclass
class FileState:
    """
    Represents the state of a file that the agent has interacted with.
    
    Tracks both the content and metadata of files that the LLM has
    created, read, or modified during the session.
    """
    filename: str
    content: str
    size: int
    last_action: str = "unknown"  # read, write, create


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
class RAGRetrievalResult:
    """
    Represents a RAG retrieval operation result.
    
    Stores the query, results, and metadata from semantic search
    operations to maintain context across iterations.
    """
    query: str
    results_count: int
    full_results: List[Dict[str, Any]]  


@dataclass
class ActionContext:
    """
    Represents context from previous actions taken by the agent.
    
    Maintains a sliding window of recent actions and their outcomes
    to provide continuity in the LLM context.
    """
    action_name: str
    arguments: Dict[str, Any]
    result: str
    iteration: int
    description: Optional[str] = None  # Human-readable description of the action


class AgentState:
    """
    Centralized state management for the Bro agent.
    
    This class maintains all context that should be included in LLM calls,
    including file states, browser tabs, RAG results, and action history.
    The state is designed to be serializable and provides formatted output
    for inclusion in LLM prompts.
    """
    
    def __init__(self, user_id: str = "default", session_id: str = "default"):
        """
        Initialize the agent state.
        
        Args:
            user_id: User identifier for session-based file management
            session_id: Session identifier for session-based file management
        """
        self.user_id = user_id
        self.session_id = session_id
        self.files: Dict[str, FileState] = {}
        self.tabs: List[TabState] = []
        self.rag_results: List[RAGRetrievalResult] = []
        self.action_history: List[ActionContext] = []
        self.max_action_history = 5  # Keep last 5 actions for context
        self.max_rag_results = 10    # Keep last 10 RAG searches
        
        # Track session metadata        
        self.current_tab_index: Optional[int] = None
        self.other_stuff: List[str] = []
        
    def add_file_state(
        self, 
        filename: str, 
        content: str, 
        action: str = "unknown",
    ) -> None:
        """
        Add or update file state information.
        
        Args:
            filename: Name of the file
            content: Current content of the file
            action: Action that was performed (read, write, create)
        """
        # Normalize filename (handle session prefixes)
        normalized_name = filename
        
        self.files[normalized_name] = FileState(
            filename=normalized_name,
            content=content,
            size=len(content),
            last_action=action
        )
    
    def get_file_content(self, filename: str) -> Optional[str]:
        """
        Get the content of a tracked file.
        
        Args:
            filename: Name of the file to retrieve
            
        Returns:
            File content if exists, None otherwise
        """
        file_state = self.files.get(filename)
        return file_state.content if file_state else None
    
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
    
    def remove_tab_state(self, url: str) -> None:
        """
        Remove the first matching tab by URL from tracking (when closed).
        If multiple tabs share the same URL, only the first occurrence is removed.
        """
        removed_index = None
        for i, tab in enumerate(self.tabs):
            if tab.url == url:
                removed_index = i
                break
        if removed_index is None:
            return
        
        del self.tabs[removed_index]
        
        # Adjust current tab index if necessary
        if self.current_tab_index is not None:
            if self.current_tab_index == removed_index:
                self.current_tab_index = min(removed_index, len(self.tabs) - 1) if self.tabs else None
            elif self.current_tab_index > removed_index:
                self.current_tab_index -= 1
    
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

    def add_rag_preview(self, preview: str) -> None:
        """
        Add RAG preview to state.
        """
        self.other_stuff.append(preview)
    
    def add_rag_result(
        self, 
        query: str, 
        results: List[Dict[str, Any]]
    ) -> None:
        """
        Add RAG retrieval results to state.
        
        Args:
            query: The search query that was performed
            results: List of search results with content and metadata
        """
        # Clear RAG previews since actual results are now available
        self.other_stuff.clear()
        
        rag_result = RAGRetrievalResult(
            query=query,
            results_count=len(results),
            full_results=results
        )
        
        self.rag_results.append(rag_result)
        
        # Keep only the most recent RAG results
        if len(self.rag_results) > self.max_rag_results:
            self.rag_results = self.rag_results[-self.max_rag_results:]
    
    def add_action_context(
        self,
        action_name: str,
        arguments: Dict[str, Any],
        result: str,
        iteration: int,
        description: Optional[str] = None,
        highlighted_elements: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Add action context to history.
        
        Args:
            action_name: Name of the action that was performed
            arguments: Arguments passed to the action
            result: Result of the action
            iteration: Iteration number when action was performed
            description: Optional human-readable description of the action
            highlighted_elements: Optional list of highlighted elements for detailed descriptions
        """
        # Generate description if not provided
        if description is None:
            description = _generate_action_description(action_name, arguments, highlighted_elements)
            
        action_context = ActionContext(
            action_name=action_name,
            arguments=arguments,
            result=result,
            iteration=iteration,
            description=description
        )
        
        self.action_history.append(action_context)
        
        # Keep only the most recent actions
        if len(self.action_history) > self.max_action_history:
            self.action_history = self.action_history[-self.max_action_history:]
    
    def get_context_for_llm(self, include_full_files: bool = True) -> str:
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
                context_parts.append(f"Current Page: {current_tab.title} ({current_tab.url}) [Tab {self.current_tab_index}]")
        
        # Browser tabs state
        if self.tabs:
            context_parts.append("\n=== OPEN BROWSER TABS ===")
            for i, tab in enumerate(self.tabs):
                status = "ACTIVE" if tab.is_active else "background"
                context_parts.append(f"[{i}] [{status}] {tab.title} ({tab.url})")
        
        # Files created/accessed by agent
        if self.files:
            context_parts.append("\n=== FILES MANAGED BY AGENT ===")
            for filename, file_state in self.files.items():
                
                context_parts.append(f"{filename} ({file_state.size} chars, {file_state.last_action})")
                
                if include_full_files and file_state.size < 2000:  # Include full content for small files
                    context_parts.append(f"Content:\n{file_state.content}")
                elif file_state.size >= 2000:  # Show preview for large files
                    preview = file_state.content[:500] + "..." if len(file_state.content) > 500 else file_state.content
                    context_parts.append(f"Content preview:\n{preview}")
                context_parts.append("")  # Empty line between files
        
        # RAG retrieval results
        if self.rag_results:
            context_parts.append("=== RAG SEARCH RESULTS ===")
            for i, rag_result in enumerate(self.rag_results, 1):  # Show all results
                context_parts.append(f"{i}. Query: '{rag_result.query}' ({rag_result.results_count} results)")
                # No preview shown - full results are only accessed when LLM explicitly reads them
        
        # Recent action history
        if self.action_history:
            context_parts.append("\n=== RECENT ACTIONS ===")
            for action in self.action_history[-3:]:  # Show last 3 actions
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
        
        if self.other_stuff:
            for stuff in self.other_stuff:
                context_parts.append(stuff)
        
        context_parts.append("=== END AGENT CONTEXT ===\n")
        
        return "\n".join(context_parts)
    
    def get_files_summary(self) -> Dict[str, Any]:
        """
        Get a summary of tracked files for debugging/monitoring.
        
        Returns:
            Dictionary with file summary information
        """
        return {
            "total_files": len(self.files),
            "total_content_size": sum(f.size for f in self.files.values()),
            "files": {name: {"size": f.size, "action": f.last_action} 
                     for name, f in self.files.items()}
        }
    
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
        self.files.clear()
        self.tabs.clear()
        self.rag_results.clear()
        self.action_history.clear()
        self.current_tab_index = None
        self.other_stuff.clear()
    def get_session_directory(self):
        """
        Get the session directory path.
        
        Returns:
            Path to the session directory
        """
        from pathlib import Path
        return Path.home() / ".bro" / self.user_id / f"session-{self.session_id}"
    
    def get_file_tree_representation(self) -> str:
        """
        Generate a tree representation of the session file structure for debugging.
        
        Returns:
            String representation of the file tree structure
        """
        from pathlib import Path
        
        session_dir = self.get_session_directory()
        
        if not session_dir.exists():
            return f"Session directory does not exist: {session_dir}"
        
        def _build_tree(path: Path, prefix: str = "", is_last: bool = True) -> List[str]:
            """Recursively build tree representation."""
            lines = []
            
            if path.is_dir():
                # Directory
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{path.name}/")
                
                # Get children and sort (directories first, then files)
                try:
                    children = list(path.iterdir())
                    children.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
                    
                    for i, child in enumerate(children):
                        is_child_last = (i == len(children) - 1)
                        child_prefix = prefix + ("    " if is_last else "│   ")
                        lines.extend(_build_tree(child, child_prefix, is_child_last))
                        
                except PermissionError:
                    lines.append(f"{prefix}    [Permission Denied]")
                    
            else:
                # File
                connector = "└── " if is_last else "├── "
                size = path.stat().st_size if path.exists() else 0
                size_str = f" ({size} bytes)" if size > 0 else ""
                lines.append(f"{prefix}{connector}{path.name}{size_str}")
                
            return lines
        
        tree_lines = [f"Session Directory Tree: {session_dir}"]
        tree_lines.extend(_build_tree(session_dir, "", True))
        
        return "\n".join(tree_lines)
    
    async def save_state_to_file(self, iteration: Optional[int] = None) -> str:
        """
        Save the current agent state to a JSON file in the session directory.
        Uses a consistent filename that gets updated on each save instead of creating new files.
        
        Args:
            iteration: Optional iteration number to include in the saved data
            
        Returns:
            Path to the saved state file
        """
        import json
        from datetime import datetime
        
        session_dir = self.get_session_directory()
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Use consistent filename that gets updated instead of creating new files
        filename = "agent_state.json"
        state_file = session_dir / filename
        
        # Convert state to dictionary
        state_data = self.to_dict()
        state_data["user_id"] = self.user_id
        state_data["session_id"] = self.session_id
        state_data["saved_at"] = datetime.now().isoformat()
        state_data["iteration"] = iteration
        
        # Save to file (overwrites existing file)
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)
            
        return str(state_file)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert state to dictionary for serialization.
        
        Returns:
            Dictionary representation of the agent state
        """
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "current_tab_index": self.current_tab_index,
            "files": {
                name: {
                    "filename": f.filename,
                    "content": f.content,
                    "size": f.size,
                    "last_action": f.last_action
                }
                for name, f in self.files.items()
            },
            "tabs": [
                {"index": i, "url": t.url, "title": t.title, "is_active": t.is_active}
                for i, t in enumerate(self.tabs)
            ],
            "rag_results_count": len(self.rag_results),
            "action_history_count": len(self.action_history),
            "other_stuff": self.other_stuff
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
