"""Tests for ReleaseExecutor parallel stage execution."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.shared.execute import ReleaseExecutor
from uv_release_monorepo.shared.models import BuildStage, PlanCommand, ReleasePlan


def _make_plan(**kwargs: object) -> ReleasePlan:
    defaults: dict = dict(
        uvr_version="0.3.0",
        rebuild_all=False,
        changed={},
        unchanged={},
        release_tags={},
        matrix=[],
    )
    defaults.update(kwargs)
    return ReleasePlan(**defaults)


def _make_executor() -> ReleaseExecutor:
    return ReleaseExecutor(_make_plan())


class TestRunPackages:
    """Tests for _run_packages parallel execution."""

    @patch("uv_release_monorepo.shared.execute.subprocess.run")
    def test_single_package_runs_sequentially(self, mock_run: MagicMock) -> None:
        """A stage with one package uses the fast sequential path."""
        mock_run.return_value = MagicMock(returncode=0)
        stage = BuildStage(
            packages={
                "pkg-a": [
                    PlanCommand(args=["uv", "version", "1.0.0"]),
                    PlanCommand(args=["uv", "build", "packages/a"]),
                ]
            }
        )
        _make_executor()._run_packages(stage)
        assert mock_run.call_count == 2

    @patch("uv_release_monorepo.shared.execute.subprocess.run")
    def test_multiple_packages_all_run(self, mock_run: MagicMock) -> None:
        """A stage with multiple packages runs all of them."""
        mock_run.return_value = MagicMock(returncode=0)
        stage = BuildStage(
            packages={
                "pkg-a": [PlanCommand(args=["uv", "build", "a"])],
                "pkg-b": [PlanCommand(args=["uv", "build", "b"])],
                "pkg-c": [PlanCommand(args=["uv", "build", "c"])],
            }
        )
        _make_executor()._run_packages(stage)
        assert mock_run.call_count == 3

    @patch("uv_release_monorepo.shared.execute.subprocess.run")
    def test_parallel_packages_run_concurrently(self, mock_run: MagicMock) -> None:
        """Packages in a multi-package stage execute in separate threads."""
        threads_seen: set[int] = set()
        barrier = threading.Barrier(2, timeout=5)

        def _track_thread(*_args: object, **_kwargs: object) -> MagicMock:
            threads_seen.add(threading.current_thread().ident or 0)
            barrier.wait()  # both threads must reach here
            return MagicMock(returncode=0)

        mock_run.side_effect = _track_thread
        stage = BuildStage(
            packages={
                "pkg-a": [PlanCommand(args=["uv", "build", "a"])],
                "pkg-b": [PlanCommand(args=["uv", "build", "b"])],
            }
        )
        _make_executor()._run_packages(stage)
        assert len(threads_seen) == 2, "Expected two distinct threads"

    @patch("uv_release_monorepo.shared.execute.subprocess.run")
    def test_failure_lets_others_finish(self, mock_run: MagicMock) -> None:
        """When one package fails, other packages in the same stage still complete."""
        call_log: list[str] = []

        def _side_effect(args: list[str], **_kw: object) -> MagicMock:
            pkg = args[-1]  # "a" or "b"
            call_log.append(pkg)
            return MagicMock(returncode=1 if pkg == "a" else 0)

        mock_run.side_effect = _side_effect
        stage = BuildStage(
            packages={
                "pkg-a": [PlanCommand(args=["uv", "build", "a"])],
                "pkg-b": [PlanCommand(args=["uv", "build", "b"])],
            }
        )
        with pytest.raises(SystemExit) as exc:
            _make_executor()._run_packages(stage)
        assert exc.value.code == 1
        # Both packages were attempted
        assert "a" in call_log
        assert "b" in call_log

    @patch("uv_release_monorepo.shared.execute.subprocess.run")
    def test_empty_packages_is_noop(self, mock_run: MagicMock) -> None:
        """A stage with no packages does nothing."""
        stage = BuildStage()
        _make_executor()._run_packages(stage)
        mock_run.assert_not_called()

    @patch("uv_release_monorepo.shared.execute.subprocess.run")
    def test_setup_runs_before_packages(self, mock_run: MagicMock) -> None:
        """Setup commands run sequentially via the build() method."""
        call_log: list[str] = []

        def _side_effect(args: list[str], **_kw: object) -> MagicMock:
            call_log.append(" ".join(args))
            return MagicMock(returncode=0)

        mock_run.side_effect = _side_effect
        plan = _make_plan(
            build_commands={
                ("ubuntu-latest",): [
                    BuildStage(
                        setup=[PlanCommand(args=["mkdir", "-p", "dist"])],
                        packages={"pkg-a": [PlanCommand(args=["uv", "build", "a"])]},
                    ),
                ]
            }
        )
        ReleaseExecutor(plan).build(runner=["ubuntu-latest"])
        assert call_log == ["mkdir -p dist", "uv build a"]


class TestBuildStages:
    """Tests for executor.build() with the new stage-based plan."""

    @patch("uv_release_monorepo.shared.execute.subprocess.run")
    def test_stages_run_in_order(self, mock_run: MagicMock) -> None:
        """Stages execute sequentially — setup before build layers."""
        call_log: list[str] = []

        def _side_effect(args: list[str], **_kw: object) -> MagicMock:
            call_log.append(" ".join(args))
            return MagicMock(returncode=0)

        mock_run.side_effect = _side_effect
        plan = _make_plan(
            build_commands={
                ("ubuntu-latest",): [
                    BuildStage(setup=[PlanCommand(args=["mkdir", "-p", "dist"])]),
                    BuildStage(
                        packages={"pkg-a": [PlanCommand(args=["uv", "build", "a"])]}
                    ),
                ]
            }
        )
        executor = ReleaseExecutor(plan)
        executor.build(runner=["ubuntu-latest"])
        assert call_log == ["mkdir -p dist", "uv build a"]
