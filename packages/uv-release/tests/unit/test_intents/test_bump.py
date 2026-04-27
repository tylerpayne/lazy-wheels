"""Tests for BumpIntent: guard and plan."""

from __future__ import annotations

import pytest

from uv_release.intents.bump import BumpIntent
from uv_release.commands import PinDepsCommand, SetVersionCommand, ShellCommand
from uv_release.types import (
    BumpType,
    Plan,
)

from ..conftest import make_package, make_workspace


# ---------------------------------------------------------------------------
# BumpIntent construction
# ---------------------------------------------------------------------------


class TestBumpIntentConstruction:
    """BumpIntent is a frozen Pydantic model with correct defaults."""

    def test_type_discriminator(self) -> None:
        intent = BumpIntent(bump_type=BumpType.MINOR)
        assert intent.type == "bump"

    def test_defaults(self) -> None:
        intent = BumpIntent(bump_type=BumpType.MINOR)
        assert intent.packages == frozenset()
        assert intent.pin is True
        assert intent.commit is True

    def test_frozen(self) -> None:
        intent = BumpIntent(bump_type=BumpType.MINOR)
        with pytest.raises(Exception):
            intent.bump_type = BumpType.MAJOR

    def test_with_packages(self) -> None:
        intent = BumpIntent(bump_type=BumpType.MINOR, packages=frozenset({"a", "b"}))
        assert intent.packages == frozenset({"a", "b"})


# ---------------------------------------------------------------------------
# BumpIntent.guard
# ---------------------------------------------------------------------------


class TestBumpGuardPackageExists:
    """guard raises ValueError when requested packages do not exist."""

    def test_unknown_package_raises(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = BumpIntent(
            bump_type=BumpType.MINOR, packages=frozenset({"nonexistent"})
        )
        with pytest.raises(ValueError, match="nonexistent"):
            intent.guard(workspace=ws)

    def test_known_package_passes(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = BumpIntent(bump_type=BumpType.MINOR, packages=frozenset({"a"}))
        intent.guard(workspace=ws)  # should not raise

    def test_empty_packages_means_all(self) -> None:
        """Empty packages set means bump all. guard should pass."""
        ws = make_workspace({"a": make_package("a"), "b": make_package("b")})
        intent = BumpIntent(bump_type=BumpType.MINOR)
        intent.guard(workspace=ws)  # should not raise


# fmt: off
_GUARD_INVALID_BUMPS: list[tuple[str, BumpType]] = [
    ("1.0.1.post0.dev0", BumpType.ALPHA),   # post -> alpha invalid
    ("1.0.1.post0.dev0", BumpType.BETA),    # post -> beta invalid
    ("1.0.1.post0.dev0", BumpType.RC),      # post -> rc invalid
    ("1.0.1b0.dev0",     BumpType.ALPHA),   # beta -> alpha invalid (backwards)
    ("1.0.1rc0.dev0",    BumpType.ALPHA),   # rc -> alpha invalid
    ("1.0.1rc0.dev0",    BumpType.BETA),    # rc -> beta invalid
    ("1.0.1a2.dev0",     BumpType.POST),    # pre-release -> post invalid
    ("1.0.1.dev0",       BumpType.POST),    # dev -> post invalid
]
# fmt: on


class TestBumpGuardVersionTransition:
    """guard raises ValueError for invalid version state transitions."""

    @pytest.mark.parametrize(
        "version,bump_type",
        _GUARD_INVALID_BUMPS,
        ids=[f"{v}+{bt.name}" for v, bt in _GUARD_INVALID_BUMPS],
    )
    def test_invalid_bump_raises(self, version: str, bump_type: BumpType) -> None:
        pkg = make_package("a", version=version)
        ws = make_workspace({"a": pkg})
        intent = BumpIntent(bump_type=bump_type)
        with pytest.raises(ValueError):
            intent.guard(workspace=ws)

    def test_valid_bump_passes(self) -> None:
        pkg = make_package("a", version="1.0.0.dev0")
        ws = make_workspace({"a": pkg})
        intent = BumpIntent(bump_type=BumpType.MINOR)
        intent.guard(workspace=ws)  # should not raise


# ---------------------------------------------------------------------------
# BumpIntent.plan
# ---------------------------------------------------------------------------


class TestBumpPlanReturnsCorrectPlan:
    """plan() returns a Plan with bump job containing correct commands."""

    def test_returns_plan(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = BumpIntent(bump_type=BumpType.MINOR)
        result = intent.plan(workspace=ws)
        assert isinstance(result, Plan)

    def test_plan_has_one_job(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = BumpIntent(bump_type=BumpType.MINOR)
        result = intent.plan(workspace=ws)
        assert len(result.jobs) == 1

    def test_job_is_named_bump(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = BumpIntent(bump_type=BumpType.MINOR)
        result = intent.plan(workspace=ws)
        assert result.jobs[0].name == "bump"

    def test_single_package_has_set_version(self) -> None:
        ws = make_workspace({"a": make_package("a", version="1.0.0.dev0")})
        intent = BumpIntent(bump_type=BumpType.MINOR)
        result = intent.plan(workspace=ws)
        job = result.jobs[0]
        set_cmds = [c for c in job.commands if isinstance(c, SetVersionCommand)]
        assert len(set_cmds) == 1
        assert set_cmds[0].version.raw == "1.1.0.dev0"

    def test_two_packages_have_two_set_versions(self) -> None:
        ws = make_workspace(
            {
                "a": make_package("a", version="1.0.0.dev0"),
                "b": make_package("b", version="2.0.0.dev0"),
            }
        )
        intent = BumpIntent(bump_type=BumpType.MINOR)
        result = intent.plan(workspace=ws)
        job = result.jobs[0]
        set_cmds = [c for c in job.commands if isinstance(c, SetVersionCommand)]
        assert len(set_cmds) == 2

    def test_restrict_to_specific_packages(self) -> None:
        """When packages is set, only bump those packages."""
        ws = make_workspace(
            {
                "a": make_package("a", version="1.0.0.dev0"),
                "b": make_package("b", version="2.0.0.dev0"),
            }
        )
        intent = BumpIntent(bump_type=BumpType.MINOR, packages=frozenset({"a"}))
        result = intent.plan(workspace=ws)
        job = result.jobs[0]
        set_cmds = [c for c in job.commands if isinstance(c, SetVersionCommand)]
        assert len(set_cmds) == 1
        assert set_cmds[0].package.name == "a"


class TestBumpPlanCommitBehavior:
    """commit flag controls whether git commit is included."""

    def test_commit_true_has_git_commit(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = BumpIntent(bump_type=BumpType.MINOR, commit=True)
        result = intent.plan(workspace=ws)
        job = result.jobs[0]
        shell_cmds = [c for c in job.commands if isinstance(c, ShellCommand)]
        commit_cmds = [c for c in shell_cmds if "commit" in c.args]
        assert len(commit_cmds) == 1

    def test_commit_false_no_git_commit(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = BumpIntent(bump_type=BumpType.MINOR, commit=False)
        result = intent.plan(workspace=ws)
        job = result.jobs[0]
        shell_cmds = [c for c in job.commands if isinstance(c, ShellCommand)]
        commit_cmds = [c for c in shell_cmds if "commit" in c.args]
        assert len(commit_cmds) == 0


class TestBumpPlanPinBehavior:
    """pin flag controls whether internal deps are pinned."""

    def test_pin_true_has_pin_commands(self) -> None:
        alpha = make_package("a", version="1.0.0.dev0")
        beta = make_package("b", version="1.0.0.dev0", dependencies=["a"])
        ws = make_workspace({"a": alpha, "b": beta})
        intent = BumpIntent(bump_type=BumpType.MINOR, pin=True)
        result = intent.plan(workspace=ws)
        job = result.jobs[0]
        pin_cmds = [c for c in job.commands if isinstance(c, PinDepsCommand)]
        assert len(pin_cmds) > 0

    def test_pin_false_no_pin_commands(self) -> None:
        alpha = make_package("a", version="1.0.0.dev0")
        beta = make_package("b", version="1.0.0.dev0", dependencies=["a"])
        ws = make_workspace({"a": alpha, "b": beta})
        intent = BumpIntent(bump_type=BumpType.MINOR, pin=False)
        result = intent.plan(workspace=ws)
        job = result.jobs[0]
        pin_cmds = [c for c in job.commands if isinstance(c, PinDepsCommand)]
        assert len(pin_cmds) == 0


class TestBumpPlanCallsGuard:
    """guard() raises on invalid state. Called by planner before plan()."""

    def test_guard_raises_on_unknown_package(self) -> None:
        ws = make_workspace({"a": make_package("a")})
        intent = BumpIntent(
            bump_type=BumpType.MINOR, packages=frozenset({"nonexistent"})
        )
        with pytest.raises(ValueError, match="nonexistent"):
            intent.guard(workspace=ws)

    def test_guard_raises_on_invalid_bump(self) -> None:
        pkg = make_package("a", version="1.0.1.dev0")
        ws = make_workspace({"a": pkg})
        intent = BumpIntent(bump_type=BumpType.POST)
        with pytest.raises(ValueError):
            intent.guard(workspace=ws)
