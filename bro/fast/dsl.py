"""Tiny line-based action language. One action per line, e.g. `click 12`."""

import re
import shlex
from typing import List, Optional

from pydantic import BaseModel

ACTIONS = {"click", "type", "press", "scroll", "goto", "search", "back", "select", "note", "done", "wait"}


class Action(BaseModel):
    name: str
    index: Optional[int] = None
    text: str = ""

    def __str__(self) -> str:
        parts = [self.name]
        if self.index is not None:
            parts.append(str(self.index))
        if self.text:
            parts.append(self.text if self.name in ("goto",) else f'"{self.text}"')
        return " ".join(parts)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        try:
            return shlex.split(value)[0]
        except ValueError:
            return value[1:-1]
    return value.lstrip("\"'") if value[:1] in "\"'" else value


def parse_line(line: str) -> Optional[Action]:
    line = line.strip().strip("`").strip()
    if not line or line.startswith("#"):
        return None
    line = re.sub(r"^[-*\d.)\s]+(?=[a-z])", "", line)
    match = re.match(r"^(\w+)\s*(.*)$", line, re.DOTALL)
    if not match:
        return None
    name, rest = match.group(1).lower(), match.group(2).strip()
    if name not in ACTIONS:
        return None
    if name in ("click", "type", "select"):
        idx_match = re.match(r"^\[?(\d+)\]?\s*(.*)$", rest, re.DOTALL)
        if not idx_match:
            return None
        return Action(name=name, index=int(idx_match.group(1)), text=_unquote(idx_match.group(2)))
    if name == "scroll":
        direction = rest.lower().split()[0] if rest else "down"
        return Action(name=name, text="up" if direction.startswith("u") else "down")
    if name in ("back", "wait"):
        return Action(name=name)
    return Action(name=name, text=_unquote(rest))


def parse(output: str) -> List[Action]:
    """Parse model output into actions; unknown lines are ignored."""
    actions: List[Action] = []
    for line in output.splitlines():
        action = parse_line(line)
        if action:
            actions.append(action)
        if action and action.name == "done":
            break
    return actions
