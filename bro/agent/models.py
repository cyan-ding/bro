from pydantic import BaseModel
from typing import Optional, Any, Dict


class Extraction(BaseModel):
    """
    Represents extracted content from a web page.

    Tracks the content, source information, and metadata of content
    that has been extracted during the session.
    """

    content: str
    source_url: str
    source_title: str
    content_length: int


class TabState(BaseModel):
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


class TodoItem(BaseModel):
    """
    Represents a single todo item in the agent's todo list.
    """

    task: str
    completed: bool = False


class StructuredOutputContext(BaseModel):
    """
    Represents structured output from LLM responses.

    Tracks thinking, evaluation of previous goals, memory, and next goals
    from the LLM's structured JSON responses.
    """

    thinking: str
    evaluation_previous_actions: str
    memory: str
    next_goal: str


class ActionContext(BaseModel):
    """
    Represents context from previous actions taken by the agent.
    """

    action_name: str
    arguments: Dict[str, Any]
    result: str
    iteration: int
    description: Optional[str] = None  # Human-readable description of the action
    structured_output: Optional[StructuredOutputContext] = None
