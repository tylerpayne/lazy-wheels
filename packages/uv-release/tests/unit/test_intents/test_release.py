"""Tests for ReleaseIntent: guard and plan."""

from __future__ import annotations

from pathlib import Path
import pytest

from uv_release.intents.release import ReleaseIntent
from uv_release.states.changes import Changes
from uv_release.states.release_tags import ReleaseTags
from uv_release.states.uvr_state import UvrState
from uv_release.states.workspace import Workspace
from uv_release.states.worktree import Worktree
from uv_release.types import (
    Change,
    CommandGroup,
    Config,
    Package,
    Plan,
    Publishing,
    Tag,
    Version,
)


def _version(raw: str) -> Version:
    return Version.parse(raw)


def _package(
    name: str, version: str = "1.0.0.dev0", dependencies: list[str] | None = None
) -> Package:
    return Package(
        name=name,
        path=f"packages/{name}",
        version=_version(version),
        dependencies=dependencies or [],
    )


def _workspace(packages: dict[str, Package]) -> Workspace:
    return Workspace(root=Path("."), packages=packages)


def _uvr_state(
    *,
    latest_package: str = "",
    python_version: str = "3.12",
    runners: dict[str, list[list[str]]] | None = None,
    publishing: Publishing | None = None,
) -> UvrState:
    return UvrState(
        config=Config(
            uvr_version="0.1.0",
            latest_package=latest_package,
            python_version=python_version,
        ),
        runners=runners or {},
        publishing=publishing or Publishing(),
        uvr_version="0.1.0",
    )


def _changes_for(packages: dict[str, Package]) -> list[Change]:
    return [
        Change(
            package=pkg,
            baseline=Tag(
                package_name=name,
                raw=f"{name}/v{pkg.version.raw}-base",
                version=pkg.version,
                is_baseline=True,
                commit="abc123",
            ),
            commit_log=f"fixed {name}",
            reason="files changed",
        )
        for name, pkg in packages.items()
    ]


def _clean_git() -> Worktree:
    return Worktree(is_dirty=False, is_ahead_or_behind=False)


def _dirty_git() -> Worktree:
    return Worktree(is_dirty=True, is_ahead_or_behind=False)


def _ahead_git() -> Worktree:
    return Worktree(is_dirty=False, is_ahead_or_behind=True)


# ---------------------------------------------------------------------------
# ReleaseIntent construction
# ---------------------------------------------------------------------------


class TestReleaseIntentConstruction:
    """ReleaseIntent is a frozen Pydantic model with correct defaults."""

    def test_type_discriminator(self) -> None:
        intent = ReleaseIntent()
        assert intent.type == "release"

    def test_defaults(self) -> None:
        intent = ReleaseIntent()
        assert intent.dev_release is False
        assert intent.target == "local"
        assert intent.skip == frozenset()


# ---------------------------------------------------------------------------
# ReleaseIntent.guard
# ---------------------------------------------------------------------------


class TestReleaseGuard:
    """guard raises ValueError for dirty worktree or out-of-sync HEAD."""

    def test_dirty_worktree_raises(self) -> None:
        _workspace({"a": _package("a")})
        intent = ReleaseIntent()
        with pytest.raises(ValueError, match="not clean"):
            intent.guard(worktree=_dirty_git())

    def test_ahead_of_remote_raises(self) -> None:
        _workspace({"a": _package("a")})
        intent = ReleaseIntent()
        with pytest.raises(ValueError, match="differs from remote"):
            intent.guard(worktree=_ahead_git())

    def test_clean_worktree_passes(self) -> None:
        _workspace({"a": _package("a")})
        intent = ReleaseIntent()
        intent.guard(worktree=_clean_git())  # should not raise


# ---------------------------------------------------------------------------
# ReleaseIntent.plan - job structure
# ---------------------------------------------------------------------------


class TestReleasePlanJobStructure:
    """plan() produces a Plan with the expected jobs."""

    def _plan_with_changes(
        self,
        ws: Workspace,
        intent: ReleaseIntent,
        changes: list[Change],
        uvr: UvrState | None = None,
    ) -> Plan:
        return intent.plan(
            workspace=ws,
            uvr_state=uvr or _uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )

    def test_returns_plan(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(ws, ReleaseIntent(), _changes_for(pkgs))
        assert isinstance(result, Plan)

    def test_has_five_jobs(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(ws, ReleaseIntent(), _changes_for(pkgs))
        assert len(result.jobs) == 5

    def test_job_names_in_order(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(ws, ReleaseIntent(), _changes_for(pkgs))
        names = [j.name for j in result.jobs]
        assert names == ["validate", "build", "release", "publish", "bump"]

    def test_no_changes_empty_plan(self) -> None:
        ws = _workspace({"a": _package("a")})
        result = self._plan_with_changes(ws, ReleaseIntent(), [])
        assert result.jobs == []


# ---------------------------------------------------------------------------
# ReleaseIntent.plan - version computation
# ---------------------------------------------------------------------------


class TestReleasePlanVersions:
    """plan() computes correct release and next versions."""

    def _plan_with_changes(
        self,
        ws: Workspace,
        intent: ReleaseIntent,
        changes: list[Change],
        uvr: UvrState | None = None,
    ) -> Plan:
        return intent.plan(
            workspace=ws,
            uvr_state=uvr or _uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )

    def test_validate_job_has_version_fix_local(self) -> None:
        """Dev package with target=local: validate job has a CommandGroup."""
        pkgs = {"a": _package("a", version="1.0.0.dev0")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws, ReleaseIntent(target="local"), _changes_for(pkgs)
        )
        validate_cmds = result.jobs[0].commands
        assert len(validate_cmds) == 1
        assert isinstance(validate_cmds[0], CommandGroup)

    def test_validate_job_ci_no_group(self) -> None:
        """CI target: version fix commands not wrapped in CommandGroup."""
        pkgs = {"a": _package("a", version="1.0.0.dev0")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws, ReleaseIntent(target="ci"), _changes_for(pkgs)
        )
        validate_cmds = result.jobs[0].commands
        assert len(validate_cmds) > 0
        assert not isinstance(validate_cmds[0], CommandGroup)

    def test_dev_release_no_version_fix(self) -> None:
        """dev_release=True: no version fix needed."""
        pkgs = {"a": _package("a", version="1.0.0.dev0")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws, ReleaseIntent(dev_release=True), _changes_for(pkgs)
        )
        validate_cmds = result.jobs[0].commands
        assert len(validate_cmds) == 0


# ---------------------------------------------------------------------------
# ReleaseIntent.plan - skip behavior
# ---------------------------------------------------------------------------


class TestReleasePlanSkip:
    """skip set controls which jobs get commands."""

    def _plan_with_changes(
        self,
        ws: Workspace,
        intent: ReleaseIntent,
        changes: list[Change],
        uvr: UvrState | None = None,
    ) -> Plan:
        return intent.plan(
            workspace=ws,
            uvr_state=uvr or _uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )

    def test_skip_build_empty_build_job(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws, ReleaseIntent(skip=frozenset({"build"})), _changes_for(pkgs)
        )
        build_job = next(j for j in result.jobs if j.name == "build")
        assert build_job.commands == []

    def test_skip_release_empty_release_job(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws, ReleaseIntent(skip=frozenset({"release"})), _changes_for(pkgs)
        )
        release_job = next(j for j in result.jobs if j.name == "release")
        assert release_job.commands == []

    def test_unskipped_jobs_have_commands(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws,
            ReleaseIntent(skip=frozenset({"release", "publish"})),
            _changes_for(pkgs),
        )
        build_job = next(j for j in result.jobs if j.name == "build")
        bump_job = next(j for j in result.jobs if j.name == "bump")
        assert len(build_job.commands) > 0
        assert len(bump_job.commands) > 0


# ---------------------------------------------------------------------------
# ReleaseIntent.plan - CI metadata
# ---------------------------------------------------------------------------


class TestReleasePlanCIMetadata:
    """plan() populates CI metadata on the Plan."""

    def _plan_with_changes(
        self,
        ws: Workspace,
        intent: ReleaseIntent,
        changes: list[Change],
        uvr: UvrState | None = None,
    ) -> Plan:
        return intent.plan(
            workspace=ws,
            uvr_state=uvr or _uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )

    def test_python_version_from_config(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        uvr = _uvr_state(python_version="3.11")
        result = self._plan_with_changes(
            ws, ReleaseIntent(), _changes_for(pkgs), uvr=uvr
        )
        assert result.python_version == "3.11"

    def test_skip_propagated(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws,
            ReleaseIntent(skip=frozenset({"build", "publish"})),
            _changes_for(pkgs),
        )
        assert "build" in result.skip
        assert "publish" in result.skip

    def test_reuse_run_propagated(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws,
            ReleaseIntent(reuse_run="12345"),
            _changes_for(pkgs),
        )
        assert result.reuse_run == "12345"

    def test_reuse_release_propagated(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws,
            ReleaseIntent(reuse_release=True),
            _changes_for(pkgs),
        )
        assert result.reuse_release is True


# ---------------------------------------------------------------------------
# ReleaseIntent.plan - reuse behavior
# ---------------------------------------------------------------------------


class TestReleasePlanReuse:
    """reuse_run and reuse_release control skip behavior."""

    def _plan_with_changes(
        self,
        ws: Workspace,
        intent: ReleaseIntent,
        changes: list[Change],
        uvr: UvrState | None = None,
    ) -> Plan:
        return intent.plan(
            workspace=ws,
            uvr_state=uvr or _uvr_state(),
            changes=Changes(items=tuple(changes)),
            release_tags=ReleaseTags(),
        )

    def test_reuse_run_skips_build(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws, ReleaseIntent(reuse_run="12345"), _changes_for(pkgs)
        )
        assert "build" in result.skip
        build_job = next(j for j in result.jobs if j.name == "build")
        assert build_job.commands == []

    def test_reuse_run_release_job_has_download(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws, ReleaseIntent(reuse_run="12345"), _changes_for(pkgs)
        )
        release_job = next(j for j in result.jobs if j.name == "release")
        labels = " ".join(c.label for c in release_job.commands)
        assert "12345" in labels

    def test_reuse_release_skips_release(self) -> None:
        pkgs = {"a": _package("a")}
        ws = _workspace(pkgs)
        result = self._plan_with_changes(
            ws, ReleaseIntent(reuse_release=True), _changes_for(pkgs)
        )
        assert "release" in result.skip
        release_job = next(j for j in result.jobs if j.name == "release")
        assert release_job.commands == []
