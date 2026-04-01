"""Tests for build_plan() and build command stage structure."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.shared.models import (
    DownloadWheelsCommand,
    PackageInfo,
    PlanConfig,
    ReleasePlan,
    ShellCommand,
)
from uv_release_monorepo.shared.planner import build_plan

from tests._helpers import _make_ctx


class TestBuildPlan:
    """Tests for build_plan()."""

    @pytest.fixture(autouse=True)
    def _mock_planner_io(self) -> None:  # type: ignore[return]
        """Mock generate_release_notes used by the planner."""
        with patch(
            "uv_release_monorepo.shared.planner._planner.generate_release_notes",
            return_value="",
        ):
            yield

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_returns_release_plan(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """build_plan returns a ReleasePlan with correct changed/unchanged split."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
        }
        mock_build_ctx.return_value = _make_ctx(
            packages,
            release_tags={
                "pkg-a": "pkg-a/v0.9.0",
                "pkg-b": "pkg-b/v0.9.0",
            },
            baselines={
                "pkg-a": "pkg-a/v1.0.0-dev",
                "pkg-b": "pkg-b/v1.0.0-dev",
            },
        )
        mock_detect.return_value = ["pkg-a"]

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        assert isinstance(plan, ReleasePlan)
        assert "pkg-a" in plan.changed
        assert "pkg-b" in plan.unchanged
        assert plan.uvr_version == "0.3.0"
        assert plan.rebuild_all is False

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_expands_matrix_for_changed_only(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Matrix entries are only created for changed packages, not unchanged."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
        }
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = ["pkg-a"]  # only pkg-a changed

        plan = build_plan(
            PlanConfig(
                rebuild_all=False,
                matrix={
                    "pkg-a": [["ubuntu-latest"], ["macos-14"]],
                    "pkg-b": [["ubuntu-latest"]],
                },
                uvr_version="0.3.0",
                dry_run=True,
            )
        )

        # Only pkg-a is changed; it has two runners
        assert "pkg-a" in plan.changed
        assert "pkg-b" not in plan.changed
        assert plan.changed["pkg-a"].runners == [["ubuntu-latest"], ["macos-14"]]
        assert len(plan.build_matrix) == 2  # ubuntu-latest + macos-14

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_defaults_matrix_to_ubuntu_latest(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Changed packages with no matrix entry default to ubuntu-latest."""
        packages = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = ["pkg-a"]

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        assert plan.changed["pkg-a"].runners == [["ubuntu-latest"]]
        assert len(plan.build_matrix) == 1

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_empty_changed_returns_empty_plan(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """When nothing changed, returns a plan with empty changed dict."""
        packages = {"pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])}
        mock_build_ctx.return_value = _make_ctx(
            packages,
            release_tags={"pkg-a": "pkg-a/v1.0.0"},
            baselines={"pkg-a": "pkg-a/v1.0.0-dev"},
        )
        mock_detect.return_value = []

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        assert plan.changed == {}
        assert "pkg-a" in plan.unchanged

    @patch("uv_release_monorepo.shared.planner._planner.generate_release_notes")
    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_populates_release_commands_and_ci_publish(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
        mock_gen_notes: MagicMock,
    ) -> None:
        """build_plan populates release_commands with git tag + publish commands."""
        from uv_release_monorepo.shared.models import PublishGithubReleaseCommand

        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
        }
        mock_build_ctx.return_value = _make_ctx(
            packages,
            release_tags={"pkg-a": "pkg-a/v0.9.0"},
        )
        mock_detect.return_value = ["pkg-a"]
        mock_gen_notes.return_value = "**Released:** pkg-a 1.0.0"

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        assert plan.ci_publish is True
        # release_commands should contain git tag, publish, and push
        assert len(plan.release_commands) >= 3
        tag_cmds = [
            c
            for c in plan.release_commands
            if isinstance(c, ShellCommand) and "tag" in c.args
        ]
        assert len(tag_cmds) == 1
        assert tag_cmds[0].args == ["git", "tag", "pkg-a/v1.0.0"]
        publish_cmds = [
            c
            for c in plan.release_commands
            if isinstance(c, PublishGithubReleaseCommand)
        ]
        assert len(publish_cmds) == 1
        assert publish_cmds[0].tag == "pkg-a/v1.0.0"
        assert publish_cmds[0].notes == "**Released:** pkg-a 1.0.0"

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_changed_package_includes_path_and_version(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """ChangedPackage includes path and release version."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
        }
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = ["pkg-a"]

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        assert plan.changed["pkg-a"].path == "packages/a"
        assert plan.changed["pkg-a"].release_version == "1.0.0"


class TestBuildCommandStages:
    """Tests for _generate_build_commands() stage structure."""

    @pytest.fixture(autouse=True)
    def _mock_planner_io(self) -> None:  # type: ignore[return]
        """Mock generate_release_notes used by the planner."""
        with patch(
            "uv_release_monorepo.shared.planner._planner.generate_release_notes",
            return_value="",
        ):
            yield

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_diamond_deps_produce_correct_layers(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Diamond dep graph produces setup + 3 build layers + cleanup stages."""
        packages = {
            "alpha": PackageInfo(path="packages/alpha", version="1.0.0", deps=[]),
            "beta": PackageInfo(path="packages/beta", version="1.0.0", deps=["alpha"]),
            "delta": PackageInfo(
                path="packages/delta", version="1.0.0", deps=["alpha"]
            ),
            "gamma": PackageInfo(path="packages/gamma", version="1.0.0", deps=["beta"]),
        }
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = list(packages)

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        stages = plan.build_commands[("ubuntu-latest",)]

        # Stage 0: setup
        assert stages[0].setup

        # Stage 1: layer 0 -- alpha (no deps)
        assert "alpha" in stages[1].packages
        assert len(stages[1].packages) == 1

        # Stage 2: layer 1 -- beta and delta (both depend on alpha only)
        assert set(stages[2].packages.keys()) == {"beta", "delta"}

        # Stage 3: layer 2 -- gamma (depends on beta)
        assert "gamma" in stages[3].packages
        assert len(stages[3].packages) == 1

        # No cleanup stage (all packages assigned to the same runner)
        assert len(stages) == 4

        # All layers should have --no-sources
        for stage, pkgs in [
            (stages[1], ["alpha"]),
            (stages[2], ["beta", "delta"]),
            (stages[3], ["gamma"]),
        ]:
            for pkg in pkgs:
                build_cmd = [
                    c for c in stage.packages[pkg] if c.label == f"Build {pkg}"
                ][0]
                assert "--no-sources" in build_cmd.args

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_no_deps_single_parallel_layer(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Independent packages all land in a single parallel build stage."""
        packages = {
            "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
            "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
            "pkg-c": PackageInfo(path="packages/c", version="1.0.0", deps=[]),
        }
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = list(packages)

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        stages = plan.build_commands[("ubuntu-latest",)]
        # setup + one layer with all 3 packages
        assert len(stages) == 2
        assert stages[0].setup
        assert set(stages[1].packages.keys()) == {"pkg-a", "pkg-b", "pkg-c"}

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_changed_dep_built_on_runner_that_needs_it(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """A changed dep not assigned to a runner is still built there."""
        # tools is pure-python (ubuntu-only), overlay depends on it (macos)
        packages = {
            "tools": PackageInfo(path="packages/tools", version="1.0.0", deps=[]),
            "overlay": PackageInfo(
                path="packages/overlay", version="1.0.0", deps=["tools"]
            ),
        }
        mock_build_ctx.return_value = _make_ctx(packages)
        mock_detect.return_value = list(packages)

        plan = build_plan(
            PlanConfig(
                rebuild_all=False,
                matrix={
                    "tools": [["ubuntu-latest"]],
                    "overlay": [["macos-14"]],
                },
                uvr_version="0.3.0",
                dry_run=True,
            )
        )

        # macos-14 runner should build both tools (layer 0) and overlay (layer 1)
        macos_stages = plan.build_commands[("macos-14",)]
        built_pkgs = {pkg for stage in macos_stages for pkg in stage.packages}
        assert "tools" in built_pkgs, "changed dep 'tools' must be built on macos-14"
        assert "overlay" in built_pkgs

        # tools wheel should be cleaned from dist/ (not assigned to macos-14)
        cleanup_stage = macos_stages[-1]
        assert cleanup_stage.cleanup
        cleanup_cmd = cleanup_stage.cleanup[0]
        assert "tools" in " ".join(cleanup_cmd.args)

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_setup_uses_fetch_command_for_unchanged_deps(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Setup stage uses DownloadWheelsCommand for unchanged dep downloads."""
        packages = {
            "tools": PackageInfo(path="packages/tools", version="1.0.0", deps=[]),
            "overlay": PackageInfo(
                path="packages/overlay", version="1.0.0", deps=["tools"]
            ),
        }
        mock_build_ctx.return_value = _make_ctx(
            packages,
            release_tags={"tools": "tools/v0.9.0", "overlay": None},
        )
        # Only overlay changed; tools is an unchanged dep
        mock_detect.return_value = ["overlay"]

        plan = build_plan(
            PlanConfig(rebuild_all=False, matrix={}, uvr_version="0.3.0", dry_run=True)
        )

        stages = plan.build_commands[("ubuntu-latest",)]
        setup = stages[0].setup

        dl_cmds = [cmd for cmd in setup if isinstance(cmd, DownloadWheelsCommand)]
        assert len(dl_cmds) == 1
        assert dl_cmds[0].packages == {"tools": "tools/v0.9.0"}
        assert dl_cmds[0].directory == "deps"

    @patch("uv_release_monorepo.shared.planner._planner.detect_changes")
    @patch("uv_release_monorepo.shared.planner._planner.build_context")
    def test_setup_fetch_on_each_runner(
        self,
        mock_build_ctx: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """Each runner's setup stage gets its own fetch command."""
        packages = {
            "lib": PackageInfo(path="packages/lib", version="1.0.0", deps=[]),
            "app": PackageInfo(path="packages/app", version="1.0.0", deps=["lib"]),
        }
        mock_build_ctx.return_value = _make_ctx(
            packages,
            release_tags={"lib": "lib/v0.9.0", "app": None},
        )
        mock_detect.return_value = ["app"]

        plan = build_plan(
            PlanConfig(
                rebuild_all=False,
                matrix={"app": [["ubuntu-latest"], ["macos-14"]]},
                uvr_version="0.3.0",
                dry_run=True,
            )
        )

        for runner_key in [("ubuntu-latest",), ("macos-14",)]:
            stages = plan.build_commands[runner_key]
            setup = stages[0].setup
            dl_cmds = [cmd for cmd in setup if isinstance(cmd, DownloadWheelsCommand)]
            assert len(dl_cmds) == 1, f"Missing fetch for {runner_key}"
            assert dl_cmds[0].packages == {"lib": "lib/v0.9.0"}
