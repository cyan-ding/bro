"""
Agent State Management for Bro

This module provides centralized state management for the Bro agent, tracking context
that should be included in LLM calls including file operations, RAG retrieval results,
open tabs, and other relevant information that persists across iterations.

@file purpose: Manages persistent agent state for context in LLM calls
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from patchright.async_api import Page


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
    last_modified: datetime
    created_by_agent: bool = False
    last_action: str = "unknown"  # read, write, create


@dataclass 
class TabState:
    """
    Represents the state of an open browser tab/page.
    
    Tracks open tabs to prevent duplicate navigation and maintain
    awareness of the current browser state.
    """
    url: str
    title: str
    is_active: bool = False
    last_accessed: datetime = field(default_factory=datetime.now)


@dataclass
class RAGRetrievalResult:
    """
    Represents a RAG retrieval operation result.
    
    Stores the query, results, and metadata from semantic search
    operations to maintain context across iterations.
    """
    query: str
    timestamp: datetime
    results_count: int
    full_results: List[Dict[str, Any]]  # Complete results with scores and metadata


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
    timestamp: datetime
    iteration: int


class AgentState:
    """
    Centralized state management for the Bro agent.
    
    This class maintains all context that should be included in LLM calls,
    including file states, browser tabs, RAG results, and action history.
    The state is designed to be serializable and provides formatted output
    for inclusion in LLM prompts.
    """
    
    def __init__(self, session_id: str):
        """
        Initialize the agent state.
        
        Args:
            session_id: Unique identifier for this agent session
        """
        self.session_id = session_id
        self.files: Dict[str, FileState] = {}
        self.tabs: Dict[str, TabState] = {}
        self.rag_results: List[RAGRetrievalResult] = []
        self.action_history: List[ActionContext] = []
        self.max_action_history = 5  # Keep last 5 actions for context
        self.max_rag_results = 10    # Keep last 10 RAG searches
        
        # Track session metadata
        self.session_start_time = datetime.now()
        self.current_page_url: Optional[str] = None
        self.current_page_title: Optional[str] = None
        self.other_stuff: List[str] = []
        
    def add_file_state(
        self, 
        filename: str, 
        content: str, 
        action: str = "unknown",
        created_by_agent: bool = False
    ) -> None:
        """
        Add or update file state information.
        
        Args:
            filename: Name of the file
            content: Current content of the file
            action: Action that was performed (read, write, create)
            created_by_agent: Whether this file was created by the agent
        """
        # Normalize filename (handle session prefixes)
        normalized_name = filename
        if filename.startswith(f"{self.session_id}_"):
            normalized_name = filename[len(f"{self.session_id}_"):]
        
        self.files[normalized_name] = FileState(
            filename=normalized_name,
            content=content,
            size=len(content),
            last_modified=datetime.now(),
            created_by_agent=created_by_agent,
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
        Add or update browser tab state.
        
        Args:
            url: URL of the tab
            title: Title of the tab
            is_active: Whether this is the currently active tab
        """
        # Mark all other tabs as inactive if this one is active
        if is_active:
            for tab in self.tabs.values():
                tab.is_active = False
        
        self.tabs[url] = TabState(
            url=url,
            title=title,
            is_active=is_active,
            last_accessed=datetime.now()
        )
        
        # Update current page tracking
        if is_active:
            self.current_page_url = url
            self.current_page_title = title
    
    def remove_tab_state(self, url: str) -> None:
        """
        Remove a tab from tracking (when closed).
        
        Args:
            url: URL of the tab to remove
        """
        if url in self.tabs:
            del self.tabs[url]
            
        # Clear current page if it was the removed tab
        if self.current_page_url == url:
            self.current_page_url = None
            self.current_page_title = None
    
    async def update_from_page(self, page: Page) -> None:
        """
        Update tab state from current page information.
        
        Args:
            page: Playwright page object to extract state from
        """
        try:
            url = page.url
            title = await page.title()
            self.add_tab_state(url, title, is_active=True)
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
            timestamp=datetime.now(),
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
        iteration: int
    ) -> None:
        """
        Add action context to history.
        
        Args:
            action_name: Name of the action that was performed
            arguments: Arguments passed to the action
            result: Result of the action
            iteration: Iteration number when action was performed
        """
        action_context = ActionContext(
            action_name=action_name,
            arguments=arguments,
            result=result,
            timestamp=datetime.now(),
            iteration=iteration
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
        context_parts.append(f"Session ID: {self.session_id}")
        context_parts.append(f"Session Duration: {datetime.now() - self.session_start_time}")
        
        # Current page information
        if self.current_page_url:
            context_parts.append(f"Current Page: {self.current_page_title} ({self.current_page_url})")
        
        # Browser tabs state
        if self.tabs:
            context_parts.append("\n=== OPEN BROWSER TABS ===")
            # Convert tabs to list for consistent ordering and indexing
            tab_list = list(self.tabs.values())
            for i, tab in enumerate(tab_list):
                status = "ACTIVE" if tab.is_active else "background"
                time_ago = datetime.now() - tab.last_accessed
                context_parts.append(f"[{i}] [{status}] {tab.title} ({tab.url}) - accessed {time_ago.seconds}s ago")
        
        # Files created/accessed by agent
        if self.files:
            context_parts.append("\n=== FILES MANAGED BY AGENT ===")
            for filename, file_state in self.files.items():
                created_indicator = "[CREATED]" if file_state.created_by_agent else "[ACCESSED]"
                time_ago = datetime.now() - file_state.last_modified
                
                context_parts.append(f"{created_indicator} {filename} ({file_state.size} chars, {file_state.last_action} {time_ago.seconds}s ago)")
                
                if include_full_files and file_state.size < 2000:  # Include full content for small files
                    context_parts.append(f"Content:\n{file_state.content}")
                elif file_state.size >= 2000:  # Show preview for large files
                    preview = file_state.content[:500] + "..." if len(file_state.content) > 500 else file_state.content
                    context_parts.append(f"Content preview:\n{preview}")
                context_parts.append("")  # Empty line between files
        
        # Recent RAG retrieval results
        if self.rag_results:
            context_parts.append("=== RECENT RAG SEARCH RESULTS ===")
            for i, rag_result in enumerate(self.rag_results[-3:], 1):  # Show last 3
                time_ago = datetime.now() - rag_result.timestamp
                context_parts.append(f"{i}. Query: '{rag_result.query}' ({rag_result.results_count} results, {time_ago.seconds}s ago)")
                # No preview shown - full results are only accessed when LLM explicitly reads them
        
        # Recent action history
        if self.action_history:
            context_parts.append("\n=== RECENT ACTIONS ===")
            for action in self.action_history[-3:]:  # Show last 3 actions
                time_ago = datetime.now() - action.timestamp
                args_str = ", ".join(f"{k}={v}" for k, v in list(action.arguments.items())[:2])  # Show first 2 args
                if len(action.arguments) > 2:
                    args_str += "..."
                
                result_preview = action.result[:100] + "..." if len(action.result) > 100 else action.result
                context_parts.append(f"- Iteration {action.iteration}: {action.action_name}({args_str}) -> {result_preview} ({time_ago.seconds}s ago)")
        
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
            "created_by_agent": sum(1 for f in self.files.values() if f.created_by_agent),
            "total_content_size": sum(f.size for f in self.files.values()),
            "files": {name: {"size": f.size, "created": f.created_by_agent, "action": f.last_action} 
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
        tab_list = list(self.tabs.values())
        if 0 <= index < len(tab_list):
            return tab_list[index]
        return None
    
    def get_tabs_summary(self) -> Dict[str, Any]:
        """
        Get a summary of tracked tabs for debugging/monitoring.
        
        Returns:
            Dictionary with tab summary information
        """
        return {
            "total_tabs": len(self.tabs),
            "active_tab": self.current_page_url,
            "tabs": {url: {"title": tab.title, "active": tab.is_active} 
                    for url, tab in self.tabs.items()}
        }
    
    def clear_state(self) -> None:
        """
        Clear all state (useful for testing or reset scenarios).
        """
        self.files.clear()
        self.tabs.clear()
        self.rag_results.clear()
        self.action_history.clear()
        self.current_page_url = None
        self.current_page_title = None
        self.other_stuff.clear()
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert state to dictionary for serialization.
        
        Returns:
            Dictionary representation of the agent state
        """
        return {
            "session_id": self.session_id,
            "session_start_time": self.session_start_time.isoformat(),
            "current_page_url": self.current_page_url,
            "current_page_title": self.current_page_title,
            "files": {
                name: {
                    "filename": f.filename,
                    "content": f.content,
                    "size": f.size,
                    "last_modified": f.last_modified.isoformat(),
                    "created_by_agent": f.created_by_agent,
                    "last_action": f.last_action
                }
                for name, f in self.files.items()
            },
            "tabs": {
                url: {
                    "url": t.url,
                    "title": t.title,
                    "is_active": t.is_active,
                    "last_accessed": t.last_accessed.isoformat()
                }
                for url, t in self.tabs.items()
            },
            "rag_results_count": len(self.rag_results),
            "action_history_count": len(self.action_history),
            "other_stuff": self.other_stuff
        }


# Global state manager instance - will be initialized by agent
_agent_state: Optional[AgentState] = None


def initialize_agent_state(session_id: str) -> AgentState:
    """
    Initialize the global agent state manager.
    
    Args:
        session_id: Unique identifier for this agent session
        
    Returns:
        Initialized AgentState instance
    """
    global _agent_state
    _agent_state = AgentState(session_id)
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
