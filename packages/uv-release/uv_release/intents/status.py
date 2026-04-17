"""StatusIntent: show workspace package status."""

from __future__ import annotations

import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..states.changes import parse_changes
from ..states.worktree import parse_git_state
from ..types import Plan, Workspace


class StatusIntent(BaseModel):
    """Intent to view workspace status. Read-only."""

    model_config = ConfigDict(frozen=True)

    type: Literal["status"] = "status"
    rebuild_all: bool = False
    rebuild: frozenset[str] = frozenset()

    def guard(self, workspace: Workspace) -> None:
        """Warn about git state issues."""
        git_state = parse_git_state()
        if git_state.is_dirty:
            print("WARNING: Working tree is not clean.", file=sys.stderr)
        if git_state.is_ahead_or_behind:
            print("WARNING: Local HEAD differs from remote.", file=sys.stderr)

    def plan(self, workspace: Workspace) -> Plan:
        """(state, intent) -> plan. Returns changes for display."""
        changes = parse_changes(
            workspace,
            rebuild_all=self.rebuild_all,
            rebuild=self.rebuild,
        )
        return Plan(changes=tuple(changes))
