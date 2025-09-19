from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field, field_validator


class ClickArgs(BaseModel):
    """Arguments for the click action."""

    target: int

class InputTextArgs(BaseModel):
    """Arguments for the input_text action."""

    target: int
    input_text: str
    login: Optional[str] = None
    retry_login: Optional[bool] = None

class ScrollArgs(BaseModel):
    """Arguments for the scroll action."""

    how_much: int

class SearchArgs(BaseModel):
    """Arguments for the search action."""

    query: Optional[str] = None
    tab_index: Optional[int] = None
    new_tab: Optional[bool] = None

class ExtractArgs(BaseModel):
    """Arguments for the extract action."""

    use_rag: bool
    file_name: str
    description: str

class RAGSearchArgs(BaseModel):
    """
    Pydantic model for search_rag tool arguments from LLM.

    This ensures proper validation and type conversion of arguments
    passed from the LLM through the agent system.
    """
    query: str = Field(description="Search query for semantic search in RAG database")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of results to return")


class FileSystemArgs(BaseModel):
    """
    Pydantic model for file_system tool arguments from LLM.

    This ensures proper validation and type conversion of arguments
    passed from the LLM through the agent system.
    """

    action: Literal["write", "read", "list_files"] = Field(
        description="Action to perform on the file system"
    )
    filename: Optional[str] = Field(
        default=None, description="Name of the file to read/write"
    )
    content: Optional[str] = Field(default=None, description="Content to write to file")


class DoneArgs(BaseModel):
    """Arguments for the done action."""

    reason: str


# Create a discriminated union for all action types
ActionUnion = Union[
    ClickArgs,
    InputTextArgs, 
    ScrollArgs,
    SearchArgs,
    ExtractArgs,
    FileSystemArgs,
    RAGSearchArgs,
    DoneArgs,
]

ALLOWED_ACTIONS = {
    "click": ClickArgs,
    "input_text": InputTextArgs,
    "scroll": ScrollArgs,
    "search": SearchArgs,
    "extract": ExtractArgs,
    "file_system": FileSystemArgs,
    "search_rag": RAGSearchArgs,
    "done": DoneArgs,
}


class Action(BaseModel):
    """Wrapper for an action with its name and arguments."""
    
    action_name: str = Field(description="The name of the action to execute")
    arguments: ActionUnion = Field(description="The arguments for the action")
    
    @field_validator("action_name")
    @classmethod
    def validate_action_name(cls, value: str) -> str:
        if value not in ALLOWED_ACTIONS:
            raise ValueError(f"Unknown action '{value}'. Allowed actions: {list(ALLOWED_ACTIONS.keys())}")
        return value
    

class StructuredOutput(BaseModel):
    """Structured JSON response contract expected from the LLM.

    The `actions` field is an ordered list of Action objects, each containing
    the action name and its validated arguments.
    """

    thinking: str
    evaluation_previous_goal: str
    memory: str
    next_goal: str
    actions: List[Action] = Field(default_factory=list)
