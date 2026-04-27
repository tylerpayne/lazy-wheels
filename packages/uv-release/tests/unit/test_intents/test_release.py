"""Tests for the release intent package: providers and intent assembly."""

from __future__ import annotations

import pytest

from uv_release.intents.release import ReleaseIntent
from uv_release.intents.release.build_job import (
    ReleaseBuildJob,
    compute_release_build_job,
)
from uv_release.intents.release.build_matrix import BuildMatrix, compute_build_matrix
from uv_release.intents.release.bump_job import BumpJob, compute_bump_job
from uv_release.intents.release.download import compute_download
from uv_release.intents.release.params import ReleaseParams
from uv_release.intents.release.publish_job import PublishJob, compute_publish_job
from uv_release.intents.release.release_job import ReleaseJob, compute_release_job
from uv_release.intents.release.releases import Releases, compute_releases
from uv_release.intents.release.version_fix import VersionFix, compute_version_fix
from uv_release.states.changes import Changes
from uv_release.states.release_tags import ReleaseTags
from uv_release.states.uvr_state import UvrState
from uv_release.states.worktree import Worktree
from uv_release.types import (
    CommandGroup,
    Package,
    Plan,
    Publishing,
    UserRecoverableError,
)

from ..conftest import (
    make_changes_for,
    make_package,
    make_uvr_state,
    make_version,
    make_workspace,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _releases_for(
    packages: dict[str, Package],
    *,
    dev_release: bool = False,
    latest_package: str = "",
) -> Releases:
    """Build Releases by calling the provider directly."""
    changes = Changes(items=tuple(make_changes_for(packages)))
    uvr = make_uvr_state(latest_package=latest_package)
    params = ReleaseParams(dev_release=dev_release)
    return compute_releases(changes, uvr, params)


def _clean_git() -> Worktree:
    return Worktree(is_dirty=False, is_ahead_or_behind=False)


def _dirty_git() -> Worktree:
    return Worktree(is_dirty=True, is_ahead_or_behind=False)


def _ahead_git() -> Worktree:
    return Worktree(is_dirty=False, is_ahead_or_behind=True)


# ---------------------------------------------------------------------------
# ReleaseParams
# ---------------------------------------------------------------------------


class TestReleaseParams:
    """ReleaseParams is a frozen Pydantic model with correct defaults."""

    def test_defaults(self) -> None:
        params = ReleaseParams()
        assert params.dev_release is False
        assert params.target == "local"
        assert params.skip == frozenset()
        assert params.reuse_run == ""
        assert params.reuse_release is False


# ---------------------------------------------------------------------------
# ReleaseIntent construction
# ---------------------------------------------------------------------------


class TestReleaseIntentConstruction:
    """ReleaseIntent is a frozen Pydantic model with type discriminator."""

    def test_type_discriminator(self) -> None:
        intent = ReleaseIntent()
        assert intent.type == "release"


# ---------------------------------------------------------------------------
# compute_releases provider
# ---------------------------------------------------------------------------


class TestComputeReleases:
    """compute_releases computes Release objects from Changes."""

    def test_computes_releases(self) -> None:
        pkgs = {"a": make_package("a")}
        releases = _releases_for(pkgs)
        assert "a" in releases.items
        assert releases.items["a"].release_version == make_version("1.0.0")
        assert releases.items["a"].next_version == make_version("1.0.1.dev0")

    def test_dev_release_preserves_version(self) -> None:
        pkgs = {"a": make_package("a", version="1.0.0.dev3")}
        releases = _releases_for(pkgs, dev_release=True)
        assert releases.items["a"].release_version == make_version("1.0.0.dev3")

    def test_release_notes_from_params(self) -> None:
        pkgs = {"a": make_package("a")}
        changes = Changes(items=tuple(make_changes_for(pkgs)))
        params = ReleaseParams(release_notes={"a": "custom notes"})
        releases = compute_releases(changes, make_uvr_state(), params)
        assert releases.items["a"].release_notes == "custom notes"

    def test_release_notes_fallback_to_commit_log(self) -> None:
        pkgs = {"a": make_package("a")}
        releases = _releases_for(pkgs)
        assert releases.items["a"].release_notes == "fixed a"

    def test_make_latest(self) -> None:
        pkgs = {"a": make_package("a"), "b": make_package("b")}
        releases = _releases_for(pkgs, latest_package="b")
        assert releases.items["a"].make_latest is False
        assert releases.items["b"].make_latest is True

    def test_empty_changes(self) -> None:
        changes = Changes(items=())
        releases = compute_releases(changes, make_uvr_state(), ReleaseParams())
        assert releases.items == {}


# ---------------------------------------------------------------------------
# compute_version_fix provider
# ---------------------------------------------------------------------------


class TestComputeVersionFix:
    """compute_version_fix builds a fix CommandGroup for dev versions."""

    def test_dev_release_no_fix(self) -> None:
        pkgs = {"a": make_package("a", version="1.0.0.dev0")}
        changes = Changes(items=tuple(make_changes_for(pkgs)))
        result = compute_version_fix(changes, ReleaseParams(dev_release=True))
        assert result.group is None

    def test_clean_versions_no_fix(self) -> None:
        pkgs = {"a": make_package("a", version="1.0.0")}
        changes = Changes(items=tuple(make_changes_for(pkgs)))
        result = compute_version_fix(changes, ReleaseParams())
        assert result.group is None

    def test_dev_versions_produce_fix(self) -> None:
        pkgs = {"a": make_package("a", version="1.0.0.dev0")}
        changes = Changes(items=tuple(make_changes_for(pkgs)))
        result = compute_version_fix(changes, ReleaseParams())
        assert result.group is not None
        assert isinstance(result.group, CommandGroup)
        assert result.group.needs_user_confirmation is True

    def test_ci_target_includes_push(self) -> None:
        pkgs = {"a": make_package("a", version="1.0.0.dev0")}
        changes = Changes(items=tuple(make_changes_for(pkgs)))
        result = compute_version_fix(changes, ReleaseParams(target="ci"))
        assert result.group is not None
        labels = [c.label for c in result.group.commands]
        assert "Push" in labels

    def test_local_target_no_push(self) -> None:
        pkgs = {"a": make_package("a", version="1.0.0.dev0")}
        changes = Changes(items=tuple(make_changes_for(pkgs)))
        result = compute_version_fix(changes, ReleaseParams(target="local"))
        assert result.group is not None
        labels = [c.label for c in result.group.commands]
        assert "Push" not in labels


# ---------------------------------------------------------------------------
# ReleaseIntent.guard
# ---------------------------------------------------------------------------


class TestReleaseGuard:
    """guard raises ValueError for dirty worktree or out-of-sync HEAD."""

    def test_dirty_worktree_raises(self) -> None:
        intent = ReleaseIntent()
        with pytest.raises(ValueError, match="not clean"):
            intent.guard(
                worktree=_dirty_git(),
                version_fix=VersionFix(),
                params=ReleaseParams(),
            )

    def test_ahead_of_remote_raises_for_ci(self) -> None:
        intent = ReleaseIntent()
        with pytest.raises(ValueError, match="differs from remote"):
            intent.guard(
                worktree=_ahead_git(),
                version_fix=VersionFix(),
                params=ReleaseParams(target="ci"),
            )

    def test_ahead_of_remote_allowed_for_local(self) -> None:
        intent = ReleaseIntent()
        intent.guard(
            worktree=_ahead_git(),
            version_fix=VersionFix(),
            params=ReleaseParams(target="local"),
        )

    def test_clean_worktree_passes(self) -> None:
        intent = ReleaseIntent()
        intent.guard(
            worktree=_clean_git(),
            version_fix=VersionFix(),
            params=ReleaseParams(),
        )

    def test_version_fix_raises_recoverable(self) -> None:
        fix_group = CommandGroup(label="fix", needs_user_confirmation=True, commands=[])
        intent = ReleaseIntent()
        with pytest.raises(UserRecoverableError) as exc_info:
            intent.guard(
                worktree=_clean_git(),
                version_fix=VersionFix(group=fix_group),
                params=ReleaseParams(),
            )
        assert exc_info.value.fix is fix_group

    def test_no_version_fix_no_error(self) -> None:
        intent = ReleaseIntent()
        intent.guard(
            worktree=_clean_git(),
            version_fix=VersionFix(),
            params=ReleaseParams(),
        )


# ---------------------------------------------------------------------------
# compute_download provider
# ---------------------------------------------------------------------------


class TestComputeDownload:
    """compute_download wraps shared download commands."""

    def test_default_commands(self) -> None:
        result = compute_download(ReleaseParams())
        assert len(result.commands) > 0

    def test_reuse_run_in_labels(self) -> None:
        result = compute_download(ReleaseParams(reuse_run="12345"))
        labels = " ".join(c.label for c in result.commands)
        assert "12345" in labels


# ---------------------------------------------------------------------------
# compute_release_job provider
# ---------------------------------------------------------------------------


class TestComputeReleaseJob:
    """compute_release_job builds tags and GitHub releases."""

    def test_skipped_returns_empty(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        download = compute_download(ReleaseParams())
        result = compute_release_job(
            releases, download, ReleaseParams(skip=frozenset({"release"}))
        )
        assert result.job.commands == []

    def test_reuse_release_returns_empty(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        download = compute_download(ReleaseParams())
        result = compute_release_job(
            releases, download, ReleaseParams(reuse_release=True)
        )
        assert result.job.commands == []

    def test_has_tag_and_release_commands(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        download = compute_download(ReleaseParams())
        result = compute_release_job(releases, download, ReleaseParams())
        labels = [c.label for c in result.job.commands]
        assert any("Tag" in label for label in labels)
        assert any("Release" in label for label in labels)

    def test_reuse_run_download_included(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        params = ReleaseParams(reuse_run="12345")
        download = compute_download(params)
        result = compute_release_job(releases, download, params)
        labels = " ".join(c.label for c in result.job.commands)
        assert "12345" in labels


# ---------------------------------------------------------------------------
# compute_publish_job provider
# ---------------------------------------------------------------------------


class TestComputePublishJob:
    """compute_publish_job builds publish commands."""

    def test_no_index_returns_empty(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        uvr = make_uvr_state()
        download = compute_download(ReleaseParams())
        result = compute_publish_job(releases, uvr, download, ReleaseParams())
        assert result.job.commands == []

    def test_skipped_returns_empty(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        uvr = make_uvr_state(publishing=Publishing(index="https://pypi.org/simple"))
        download = compute_download(ReleaseParams())
        result = compute_publish_job(
            releases, uvr, download, ReleaseParams(skip=frozenset({"publish"}))
        )
        assert result.job.commands == []

    def test_with_index_has_publish_commands(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        uvr = make_uvr_state(publishing=Publishing(index="https://pypi.org/simple"))
        download = compute_download(ReleaseParams())
        result = compute_publish_job(releases, uvr, download, ReleaseParams())
        labels = [c.label for c in result.job.commands]
        assert any("Publish" in label for label in labels)


# ---------------------------------------------------------------------------
# compute_bump_job provider
# ---------------------------------------------------------------------------


class TestComputeBumpJob:
    """compute_bump_job builds version bump commands."""

    def test_skipped_returns_empty(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        result = compute_bump_job(releases, ReleaseParams(skip=frozenset({"bump"})))
        assert result.job.commands == []

    def test_has_bump_commands(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        result = compute_bump_job(releases, ReleaseParams(target="ci"))
        labels = [c.label for c in result.job.commands]
        assert any("Bump" in label for label in labels)

    def test_local_target_wraps_in_command_group(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        result = compute_bump_job(releases, ReleaseParams(target="local"))
        assert len(result.job.commands) == 1
        assert isinstance(result.job.commands[0], CommandGroup)

    def test_ci_target_no_command_group(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        result = compute_bump_job(releases, ReleaseParams(target="ci"))
        assert not any(isinstance(c, CommandGroup) for c in result.job.commands)


# ---------------------------------------------------------------------------
# compute_release_build_job provider
# ---------------------------------------------------------------------------


class TestComputeReleaseBuildJob:
    """compute_release_build_job delegates to shared build job."""

    def test_skipped_returns_empty(self) -> None:
        pkgs = {"a": make_package("a")}
        releases = _releases_for(pkgs)
        result = compute_release_build_job(
            make_workspace(pkgs),
            releases,
            ReleaseTags(),
            make_uvr_state(),
            ReleaseParams(skip=frozenset({"build"})),
        )
        assert result.job.commands == []

    def test_reuse_run_returns_empty(self) -> None:
        pkgs = {"a": make_package("a")}
        releases = _releases_for(pkgs)
        result = compute_release_build_job(
            make_workspace(pkgs),
            releases,
            ReleaseTags(),
            make_uvr_state(),
            ReleaseParams(reuse_run="12345"),
        )
        assert result.job.commands == []

    def test_has_build_commands(self) -> None:
        pkgs = {"a": make_package("a")}
        releases = _releases_for(pkgs)
        result = compute_release_build_job(
            make_workspace(pkgs),
            releases,
            ReleaseTags(),
            make_uvr_state(),
            ReleaseParams(),
        )
        assert len(result.job.commands) > 0


# ---------------------------------------------------------------------------
# compute_build_matrix provider
# ---------------------------------------------------------------------------


class TestComputeBuildMatrix:
    """compute_build_matrix collects runner sets."""

    def test_default_runners(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        result = compute_build_matrix(releases, make_uvr_state())
        assert result.runners == [["ubuntu-latest"]]

    def test_custom_runners(self) -> None:
        releases = _releases_for({"a": make_package("a")})
        uvr = make_uvr_state(runners={"a": [["ubuntu-latest"], ["macos-latest"]]})
        result = compute_build_matrix(releases, uvr)
        assert ["ubuntu-latest"] in result.runners
        assert ["macos-latest"] in result.runners


# ---------------------------------------------------------------------------
# ReleaseIntent.plan - assembly
# ---------------------------------------------------------------------------


class TestReleasePlanAssembly:
    """plan() assembles pre-computed providers into a Plan."""

    def _build_plan(
        self,
        pkgs: dict[str, Package] | None = None,
        params: ReleaseParams | None = None,
        uvr: UvrState | None = None,
    ) -> Plan:
        pkgs = pkgs or {"a": make_package("a")}
        params = params or ReleaseParams()
        uvr = uvr or make_uvr_state()
        releases = _releases_for(pkgs)
        return ReleaseIntent().plan(
            releases=releases,
            release_build_job=compute_release_build_job(
                make_workspace(pkgs),
                releases,
                ReleaseTags(),
                uvr,
                params,
            ),
            release_job=compute_release_job(
                releases,
                compute_download(params),
                params,
            ),
            publish_job=compute_publish_job(
                releases,
                uvr,
                compute_download(params),
                params,
            ),
            bump_job=compute_bump_job(releases, params),
            build_matrix=compute_build_matrix(releases, uvr),
            uvr_state=uvr,
            params=params,
        )

    def test_returns_plan(self) -> None:
        result = self._build_plan()
        assert isinstance(result, Plan)

    def test_has_five_jobs(self) -> None:
        result = self._build_plan()
        assert len(result.jobs) == 5

    def test_job_names_in_order(self) -> None:
        result = self._build_plan()
        names = [j.name for j in result.jobs]
        assert names == ["validate", "build", "release", "publish", "bump"]

    def test_no_changes_empty_plan(self) -> None:
        releases = Releases()
        params = ReleaseParams()
        result = ReleaseIntent().plan(
            releases=releases,
            release_build_job=ReleaseBuildJob(),
            release_job=ReleaseJob(),
            publish_job=PublishJob(),
            bump_job=BumpJob(),
            build_matrix=BuildMatrix(),
            uvr_state=make_uvr_state(),
            params=params,
        )
        assert result.jobs == []

    def test_validate_job_always_empty(self) -> None:
        result = self._build_plan()
        assert result.jobs[0].commands == []

    def test_python_version_from_config(self) -> None:
        uvr = make_uvr_state(python_version="3.11")
        result = self._build_plan(uvr=uvr)
        assert result.python_version == "3.11"

    def test_skip_propagated(self) -> None:
        params = ReleaseParams(skip=frozenset({"build", "publish"}))
        result = self._build_plan(params=params)
        assert "build" in result.skip
        assert "publish" in result.skip

    def test_reuse_run_propagated(self) -> None:
        params = ReleaseParams(reuse_run="12345")
        result = self._build_plan(params=params)
        assert result.reuse_run == "12345"

    def test_reuse_release_propagated(self) -> None:
        params = ReleaseParams(reuse_release=True)
        result = self._build_plan(params=params)
        assert result.reuse_release is True

    def test_reuse_run_skips_build(self) -> None:
        params = ReleaseParams(reuse_run="12345")
        result = self._build_plan(params=params)
        assert "build" in result.skip
        build_job = next(j for j in result.jobs if j.name == "build")
        assert build_job.commands == []

    def test_reuse_release_skips_release(self) -> None:
        params = ReleaseParams(reuse_release=True)
        result = self._build_plan(params=params)
        assert "release" in result.skip
        release_job = next(j for j in result.jobs if j.name == "release")
        assert release_job.commands == []

    def test_skip_build_empty_build_job(self) -> None:
        params = ReleaseParams(skip=frozenset({"build"}))
        result = self._build_plan(params=params)
        build_job = next(j for j in result.jobs if j.name == "build")
        assert build_job.commands == []

    def test_skip_release_empty_release_job(self) -> None:
        params = ReleaseParams(skip=frozenset({"release"}))
        result = self._build_plan(params=params)
        release_job = next(j for j in result.jobs if j.name == "release")
        assert release_job.commands == []

    def test_unskipped_jobs_have_commands(self) -> None:
        params = ReleaseParams(skip=frozenset({"release", "publish"}))
        result = self._build_plan(params=params)
        build_job = next(j for j in result.jobs if j.name == "build")
        bump_job = next(j for j in result.jobs if j.name == "bump")
        assert len(build_job.commands) > 0
        assert len(bump_job.commands) > 0
