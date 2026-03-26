"""Tests for uv_release_monorepo.workflow_steps."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.models import MatrixEntry, PackageInfo, ReleasePlan
from uv_release_monorepo.workflow_steps import (
    execute_build,
    execute_build_all,
    execute_fetch_unchanged,
    execute_finalize,
    execute_publish_releases,
    execute_release,
    main,
)


def _make_plan_json(
    changed: list[str],
    unchanged: list[str],
    *,
    ci_publish: bool = False,
) -> str:
    """Helper to build a minimal ReleasePlan JSON string."""
    all_pkgs = changed + unchanged
    packages = {
        name: PackageInfo(path=f"packages/{name}", version="1.0.0", deps=[])
        for name in all_pkgs
    }
    plan = ReleasePlan(
        uvr_version="0.3.0",
        rebuild_all=False,
        changed={name: packages[name] for name in changed},
        unchanged={name: packages[name] for name in unchanged},
        release_tags={name: None for name in all_pkgs},
        matrix=[
            MatrixEntry(
                package=name,
                runner="ubuntu-latest",
                path=f"packages/{name}",
                version="1.0.0",
            )
            for name in changed
        ],
        ci_publish=ci_publish,
    )
    return plan.model_dump_json()


@patch("uv_release_monorepo.workflow_steps.build_packages")
def test_execute_build_builds_changed_package(mock_build: MagicMock) -> None:
    """execute_build calls build_packages when package is in changed."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_build(plan_json, "pkg-a")
    mock_build.assert_called_once()


@patch("uv_release_monorepo.workflow_steps.build_packages")
def test_execute_build_skips_unchanged_package(mock_build: MagicMock) -> None:
    """execute_build is a no-op when package is not in changed."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_build(plan_json, "pkg-b")
    mock_build.assert_not_called()


@patch("uv_release_monorepo.workflow_steps.fetch_unchanged_wheels")
def test_execute_fetch_unchanged_calls_fetch(mock_fetch: MagicMock) -> None:
    """execute_fetch_unchanged calls fetch_unchanged_wheels with plan data."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_fetch_unchanged(plan_json)
    mock_fetch.assert_called_once()


@patch("uv_release_monorepo.workflow_steps.publish_release")
def test_execute_publish_releases_calls_publish(mock_publish: MagicMock) -> None:
    """execute_publish_releases calls publish_release with plan data."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_publish_releases(plan_json)
    mock_publish.assert_called_once()


@patch("uv_release_monorepo.workflow_steps.git")
@patch("uv_release_monorepo.workflow_steps.tag_baselines")
@patch("uv_release_monorepo.workflow_steps.commit_bumps")
@patch("uv_release_monorepo.workflow_steps.apply_bumps")
@patch("uv_release_monorepo.workflow_steps.tag_changed_packages")
def test_execute_finalize_calls_sequence(
    mock_tag_pkg: MagicMock,
    mock_apply: MagicMock,
    mock_commit: MagicMock,
    mock_tag_dev: MagicMock,
    mock_git: MagicMock,
) -> None:
    """execute_finalize with ci_publish=False creates release tags, no push."""
    mock_apply.return_value = {}
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_finalize(plan_json)

    mock_tag_pkg.assert_called_once()
    mock_apply.assert_called_once()
    mock_commit.assert_called_once()
    mock_tag_dev.assert_called_once()
    # ci_publish=False: no git config, no push
    mock_git.assert_not_called()


@patch("uv_release_monorepo.workflow_steps.git")
@patch("uv_release_monorepo.workflow_steps.tag_baselines")
@patch("uv_release_monorepo.workflow_steps.commit_bumps")
@patch("uv_release_monorepo.workflow_steps.apply_bumps")
@patch("uv_release_monorepo.workflow_steps.tag_changed_packages")
def test_execute_finalize_ci_publish_skips_tags_and_pushes(
    mock_tag_pkg: MagicMock,
    mock_apply: MagicMock,
    mock_commit: MagicMock,
    mock_tag_dev: MagicMock,
    mock_git: MagicMock,
) -> None:
    """execute_finalize with ci_publish=True skips release tags, configures git, pushes."""
    mock_apply.return_value = {}
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"], ci_publish=True)
    execute_finalize(plan_json)

    mock_tag_pkg.assert_not_called()
    mock_apply.assert_called_once()
    mock_commit.assert_called_once()
    mock_tag_dev.assert_called_once()
    # ci_publish=True: git config + push
    git_calls = [c[0] for c in mock_git.call_args_list]
    assert ("config", "user.name", "github-actions[bot]") in git_calls
    assert ("push",) in git_calls
    assert ("push", "--tags") in git_calls


@patch("uv_release_monorepo.workflow_steps.git")
@patch("uv_release_monorepo.workflow_steps.tag_baselines")
@patch("uv_release_monorepo.workflow_steps.commit_bumps")
@patch("uv_release_monorepo.workflow_steps.apply_bumps")
@patch("uv_release_monorepo.workflow_steps.tag_changed_packages")
@patch("uv_release_monorepo.workflow_steps.publish_release")
@patch("uv_release_monorepo.workflow_steps.fetch_unchanged_wheels")
def test_execute_release_calls_full_sequence(
    mock_fetch: MagicMock,
    mock_publish: MagicMock,
    mock_tag_pkg: MagicMock,
    mock_apply: MagicMock,
    mock_commit: MagicMock,
    mock_tag_dev: MagicMock,
    mock_git: MagicMock,
) -> None:
    """execute_release runs the full post-build release sequence."""
    mock_apply.return_value = {}
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_release(plan_json)

    mock_fetch.assert_called_once()
    mock_publish.assert_called_once()
    mock_tag_pkg.assert_called_once()
    mock_apply.assert_called_once()
    mock_commit.assert_called_once()
    mock_tag_dev.assert_called_once()


@patch("uv_release_monorepo.workflow_steps.execute_build")
def test_main_dispatches_execute_build(mock_exec_build: MagicMock) -> None:
    """main dispatches execute-build subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["execute-build", "--plan", plan_json, "--package", "pkg-a"])
    mock_exec_build.assert_called_once_with(plan_json, "pkg-a")


@patch("uv_release_monorepo.workflow_steps.execute_release")
def test_main_dispatches_execute_release(mock_exec_release: MagicMock) -> None:
    """main dispatches execute-release subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["execute-release", "--plan", plan_json])
    mock_exec_release.assert_called_once_with(plan_json)


@patch("uv_release_monorepo.workflow_steps.execute_fetch_unchanged")
def test_main_dispatches_fetch_unchanged(mock_fetch: MagicMock) -> None:
    """main dispatches fetch-unchanged subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["fetch-unchanged", "--plan", plan_json])
    mock_fetch.assert_called_once_with(plan_json)


@patch("uv_release_monorepo.workflow_steps.execute_publish_releases")
def test_main_dispatches_publish_releases(mock_publish: MagicMock) -> None:
    """main dispatches publish-releases subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["publish-releases", "--plan", plan_json])
    mock_publish.assert_called_once_with(plan_json)


@patch("uv_release_monorepo.workflow_steps.execute_finalize")
def test_main_dispatches_finalize(mock_finalize: MagicMock) -> None:
    """main dispatches finalize subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["finalize", "--plan", plan_json])
    mock_finalize.assert_called_once_with(plan_json)


def test_main_requires_step_arg(capsys: pytest.CaptureFixture[str]) -> None:
    """main errors when no step arg is provided."""
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2
    assert "required: command" in capsys.readouterr().err


def test_main_rejects_unknown_step(capsys: pytest.CaptureFixture[str]) -> None:
    """main errors on unknown step arg."""
    with pytest.raises(SystemExit) as excinfo:
        main(["not-a-step"])
    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@patch("uv_release_monorepo.workflow_steps.execute_build_all")
def test_main_dispatches_build_all(mock_build_all: MagicMock) -> None:
    """main dispatches build-all subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["build-all", "--plan", plan_json, "--runner", "ubuntu-latest"])
    mock_build_all.assert_called_once_with(plan_json, "ubuntu-latest")


class TestExecuteBuildAll:
    """Tests for the build-all workflow step."""

    @staticmethod
    def _plan_json_with_deps() -> str:
        """Plan where beta depends on alpha, both assigned to ubuntu-latest."""
        alpha = PackageInfo(path="packages/alpha", version="1.0.0", deps=[])
        beta = PackageInfo(path="packages/beta", version="2.0.0", deps=["alpha"])
        plan = ReleasePlan(
            uvr_version="0.3.0",
            rebuild_all=False,
            changed={"alpha": alpha, "beta": beta},
            unchanged={},
            release_tags={"alpha": None, "beta": None},
            matrix=[
                MatrixEntry(
                    package="alpha",
                    runner="ubuntu-latest",
                    path="packages/alpha",
                    version="1.0.0",
                ),
                MatrixEntry(
                    package="beta",
                    runner="ubuntu-latest",
                    path="packages/beta",
                    version="2.0.0",
                ),
            ],
            runners=["ubuntu-latest"],
        )
        return plan.model_dump_json()

    @staticmethod
    def _plan_json_with_unchanged_dep() -> str:
        """Plan where beta depends on alpha, but alpha is unchanged."""
        alpha = PackageInfo(path="packages/alpha", version="1.0.0", deps=[])
        beta = PackageInfo(path="packages/beta", version="2.0.0", deps=["alpha"])
        plan = ReleasePlan(
            uvr_version="0.3.0",
            rebuild_all=False,
            changed={"beta": beta},
            unchanged={"alpha": alpha},
            release_tags={"alpha": "alpha/v1.0.0", "beta": None},
            matrix=[
                MatrixEntry(
                    package="beta",
                    runner="ubuntu-latest",
                    path="packages/beta",
                    version="2.0.0",
                ),
            ],
            runners=["ubuntu-latest"],
        )
        return plan.model_dump_json()

    @patch("uv_release_monorepo.shell.run")
    @patch("uv_release_monorepo.shell.step")
    @patch("uv_release_monorepo.deps.rewrite_pyproject")
    @patch("uv_release_monorepo.versions.strip_dev", side_effect=lambda v: v)
    def test_builds_in_topo_order(
        self,
        _mock_strip: MagicMock,
        _mock_rewrite: MagicMock,
        _mock_step: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """build-all builds alpha before beta (dependency order)."""
        mock_run.return_value = MagicMock(returncode=0)
        plan_json = self._plan_json_with_deps()

        with patch("pathlib.Path.mkdir"), patch("pathlib.Path.glob", return_value=[]):
            execute_build_all(plan_json, "ubuntu-latest")

        # Extract the package paths from uv build calls
        build_calls = [
            c for c in mock_run.call_args_list if c[0][0] == "uv" and c[0][1] == "build"
        ]
        assert len(build_calls) == 2
        assert build_calls[0][0][2] == "packages/alpha"
        assert build_calls[1][0][2] == "packages/beta"

    @patch("uv_release_monorepo.shell.run")
    @patch("uv_release_monorepo.shell.step")
    @patch("uv_release_monorepo.deps.rewrite_pyproject")
    @patch("uv_release_monorepo.versions.strip_dev", side_effect=lambda v: v)
    @patch("uv_release_monorepo.workflow_steps.fetch_unchanged_wheels")
    def test_fetches_unchanged_deps(
        self,
        mock_fetch: MagicMock,
        _mock_strip: MagicMock,
        _mock_rewrite: MagicMock,
        _mock_step: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """build-all fetches wheels for unchanged deps before building."""
        mock_run.return_value = MagicMock(returncode=0)
        plan_json = self._plan_json_with_unchanged_dep()

        with patch("pathlib.Path.mkdir"), patch("pathlib.Path.glob", return_value=[]):
            execute_build_all(plan_json, "ubuntu-latest")

        # Should have fetched alpha (unchanged dep)
        mock_fetch.assert_called_once()
        fetched_pkgs = mock_fetch.call_args[0][0]
        assert "alpha" in fetched_pkgs

    @patch("uv_release_monorepo.shell.run")
    @patch("uv_release_monorepo.shell.step")
    @patch("uv_release_monorepo.deps.rewrite_pyproject")
    @patch("uv_release_monorepo.versions.strip_dev", side_effect=lambda v: v)
    def test_passes_find_links(
        self,
        _mock_strip: MagicMock,
        _mock_rewrite: MagicMock,
        _mock_step: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """build-all passes --find-links dist/ to uv build."""
        mock_run.return_value = MagicMock(returncode=0)
        plan_json = self._plan_json_with_deps()

        with patch("pathlib.Path.mkdir"), patch("pathlib.Path.glob", return_value=[]):
            execute_build_all(plan_json, "ubuntu-latest")

        build_calls = [
            c for c in mock_run.call_args_list if c[0][0] == "uv" and c[0][1] == "build"
        ]
        for call in build_calls:
            args = call[0]
            assert "--find-links" in args
            assert "dist/" in args

    def test_skips_unassigned_runner(self, capsys: pytest.CaptureFixture[str]) -> None:
        """build-all does nothing for a runner with no assigned packages."""
        plan_json = self._plan_json_with_deps()
        execute_build_all(plan_json, "macos-latest")
        assert "No packages assigned" in capsys.readouterr().out
