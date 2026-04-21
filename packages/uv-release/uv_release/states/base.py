"""Base class for injectable state types."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class State(BaseModel):
    """Base for all injectable state types.

    Subclasses implement a parse() classmethod that declares its own
    dependencies via type hints. The planner inspects parse() and
    recursively resolves each dependency before calling it.
    """

    model_config = ConfigDict(frozen=True)
