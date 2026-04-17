"""Tests for StatusIntent: guard and plan."""

from __future__ import annotations

from unittest.mock import patch

from uv_release.intents.status import StatusIntent
from uv_release.types import (
    Config,
    Package,
    Plan,
    Publishing,
    Version,
    Workspace,
)


def _version(raw: str) -> Version:
    return Version.parse(raw)


def _package(name: str, version: str = "1.0.0.dev0") -> Package:
    return Package(name=name, path=f"packages/{name}", version=_version(version))


def _workspace(packages: dict[str, Package]) -> Workspace:
    return Workspace(
        packages=packages,
        config=Config(uvr_version="0.1.0"),
        runners={},
        publishing=Publishing(),
    )


# ---------------------------------------------------------------------------
# StatusIntent construction
# ---------------------------------------------------------------------------


class TestStatusIntentConstruction:
    """StatusIntent is a frozen Pydantic model with correct defaults."""

    def test_type_discriminator(self) -> None:
        intent = StatusIntent()
        assert intent.type == "status"

    def test_defaults(self) -> None:
        intent = StatusIntent()
        assert intent.rebuild_all is False
        assert intent.rebuild == frozenset()


# ---------------------------------------------------------------------------
# StatusIntent.guard
# ---------------------------------------------------------------------------


class TestStatusGuard:
    """Status is read-only. guard never raises."""

    def test_guard_always_passes(self) -> None:
        ws = _workspace({"a": _package("a")})
        intent = StatusIntent()
        intent.guard(ws)  # should not raise

    def test_guard_passes_with_empty_workspace(self) -> None:
        ws = _workspace({})
        intent = StatusIntent()
        intent.guard(ws)  # should not raise


# ---------------------------------------------------------------------------
# StatusIntent.plan
# ---------------------------------------------------------------------------


class TestStatusPlan:
    """plan() returns a Plan with no jobs (read-only)."""

    def test_returns_plan(self) -> None:
        ws = _workspace({"a": _package("a")})
        intent = StatusIntent()
        with patch("uv_release.intents.status.parse_changes", return_value=[]):
            result = intent.plan(ws)
        assert isinstance(result, Plan)

    def test_no_jobs(self) -> None:
        ws = _workspace({"a": _package("a")})
        intent = StatusIntent()
        with patch("uv_release.intents.status.parse_changes", return_value=[]):
            result = intent.plan(ws)
        assert result.jobs == []
