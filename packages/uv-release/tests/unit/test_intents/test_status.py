"""Tests for StatusIntent: guard and plan."""

from __future__ import annotations

from uv_release.intents.status import StatusIntent
from uv_release.states.changes import Changes
from uv_release.states.worktree import Worktree
from uv_release.types import (
    Plan,
)

from ..conftest import make_package, make_workspace


# ---------------------------------------------------------------------------
# StatusIntent construction
# ---------------------------------------------------------------------------


class TestStatusIntentConstruction:
    """StatusIntent is a frozen Pydantic model with correct defaults."""

    def test_type_discriminator(self) -> None:
        intent = StatusIntent()
        assert intent.type == "status"


# ---------------------------------------------------------------------------
# StatusIntent.guard
# ---------------------------------------------------------------------------


class TestStatusGuard:
    """Status is read-only. guard never raises."""

    def test_guard_always_passes(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = StatusIntent()
        intent.guard(workspace=ws, worktree=Worktree())  # should not raise

    def test_guard_passes_with_empty_workspace(self) -> None:
        ws = make_workspace({})
        intent = StatusIntent()
        intent.guard(workspace=ws, worktree=Worktree())  # should not raise


# ---------------------------------------------------------------------------
# StatusIntent.plan
# ---------------------------------------------------------------------------


class TestStatusPlan:
    """plan() returns a Plan with no jobs (read-only)."""

    def test_returns_plan(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = StatusIntent()
        result = intent.plan(workspace=ws, changes=Changes())
        assert isinstance(result, Plan)

    def test_no_jobs(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = StatusIntent()
        result = intent.plan(workspace=ws, changes=Changes())
        assert result.jobs == []
