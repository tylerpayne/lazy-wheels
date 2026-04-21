"""StatusIntent: show workspace package status."""

from __future__ import annotations

import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..states.changes import Changes
from ..states.workspace import Workspace
from ..states.worktree import Worktree
from ..types import Plan


class StatusIntent(BaseModel):
    """Intent to view workspace status. Read-only."""

    model_config = ConfigDict(frozen=True)

    type: Literal["status"] = "status"

    def guard(self, *, workspace: Workspace, worktree: Worktree) -> None:
        """Warn about git state issues."""
        if worktree.is_dirty:
            print("WARNING: Working tree is not clean.", file=sys.stderr)
        if worktree.is_ahead_or_behind:
            print("WARNING: Local HEAD differs from remote.", file=sys.stderr)

    def plan(self, *, workspace: Workspace, changes: Changes) -> Plan:
        """(state, intent) -> plan. Returns changes for display."""
        return Plan(changes=changes.items)
