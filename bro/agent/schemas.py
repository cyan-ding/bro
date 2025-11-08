from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator


class ClickArgs(BaseModel):
    """Arguments for the click action."""

    target: int

class InputTextArgs(BaseModel):
    """Arguments for the input_text action."""

    target: int
    input_text: str

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

    # Dummy field to satisfy Vertex AI schema requirements (no empty objects allowed)
    dummy: Optional[bool] = None





class TodoItem(BaseModel):
    """A single todo item."""

    task: str
    completed: bool = False


class TodoEditArgs(BaseModel):
    """Arguments for the todo_edit action."""

    todo_items: List[TodoItem]


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
    TodoEditArgs,
    DoneArgs,
]

ALLOWED_ACTIONS = {
    "click": ClickArgs,
    "input_text": InputTextArgs,
    "scroll": ScrollArgs,
    "search": SearchArgs,
    "extract": ExtractArgs,
    "todo_edit": TodoEditArgs,
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
    evaluation_previous_actions: str
    memory: str
    next_goal: str
    actions: List[Action] = Field(default_factory=list)
