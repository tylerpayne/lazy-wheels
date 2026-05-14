"""Tests for the release pipeline plan structure.

These tests verify that the plan produced by `uvr release --json` contains
the correct jobs, commands, and ordering for various workspace configurations.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import diny
import pytest

import tomlkit

from conftest import get_plan_json, git, read_toml, run_cli


def _commands_of_type(plan: dict, job_name: str, cmd_type: str) -> list[dict]:
    """Extract commands of a given type from a job in the plan."""
    for job in plan["jobs"]:
        if job["name"] == job_name:
            return [c for c in job["commands"] if c["type"] == cmd_type]
    return []


def _job(plan: dict, name: str) -> dict:
    for job in plan["jobs"]:
        if job["name"] == name:
            return job
    raise KeyError(f"No job named {name}")


def _set_runners(root: Path, runners: dict[str, list[list[str]]]) -> None:
    """Patch [tool.uvr.runners] in the root pyproject.toml and commit."""
    doc = tomlkit.loads((root / "pyproject.toml").read_text())
    doc["tool"]["uvr"]["runners"] = runners  # type: ignore[index]
    (root / "pyproject.toml").write_text(tomlkit.dumps(doc))
    git(root, "add", ".")
    git(root, "commit", "-m", "set runners")


class TestBuildJobStructure:
    """Verify build job has correct download and build commands in order."""

    def test_released_dep_downloaded_to_deps(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        downloads = _commands_of_type(plan, "build", "download_wheels")
        assert len(downloads) == 1
        assert downloads[0]["tag_name"] == "pkg-a/v1.0.0"
        assert downloads[0]["output_dir"] == "deps"

    def test_build_targets_go_to_dist(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        target_names = [b["label"] for b in builds]
        assert "Build pkg-b" in target_names
        assert "Build pkg-c" in target_names
        for b in builds:
            assert b["out_dir"] == "dist"

    def test_build_order_respects_dependency_chain(
        self, released_workspace: Path
    ) -> None:
        """pkg-b must build before pkg-c (pkg-c depends on pkg-b)."""
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        labels = [b["label"] for b in builds]
        assert labels.index("Build pkg-b") < labels.index("Build pkg-c")

    def test_creates_dist_and_deps_dirs(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        mkdirs = _commands_of_type(plan, "build", "make_directory")
        paths = {m["path"] for m in mkdirs}
        assert "dist" in paths
        assert "deps" in paths

    def test_pkg_a_not_in_build_commands(self, released_workspace: Path) -> None:
        """pkg-a is released. It should be downloaded, not built."""
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        assert not any("pkg-a" in b["label"] for b in builds)


class TestBuildRequiresDependency:
    """Verify build-system.requires workspace deps are discovered and ordered.

    With auto-detection (no --packages), all untagged packages are targets.
    pkg-d is untagged so it becomes a target alongside pkg-b and pkg-c.
    The build-requires relationship still affects topo ordering.

    With --packages pkg-b pkg-c, pkg-d is excluded from targets but
    discovered as an unreleased build dep of pkg-c via build-system.requires.
    """

    def test_untagged_build_dep_is_target(self, build_requires_workspace: Path) -> None:
        """pkg-d is untagged, so auto-detection picks it up as a build target."""
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        assert any("pkg-d" in b["label"] for b in builds)

    def test_untagged_build_dep_goes_to_dist(
        self, build_requires_workspace: Path
    ) -> None:
        """As a build target, pkg-d's wheel goes to dist/ for release."""
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        pkg_d_build = next(b for b in builds if "pkg-d" in b["label"])
        assert pkg_d_build["out_dir"] == "dist"

    def test_build_dep_ordered_before_dependent(
        self, build_requires_workspace: Path
    ) -> None:
        """pkg-d must build before pkg-c because pkg-c build-requires pkg-d."""
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        labels = [b["label"] for b in builds]
        assert labels.index("Build pkg-d") < labels.index("Build pkg-c")

    def test_released_build_dep_is_downloaded(
        self, build_requires_workspace: Path
    ) -> None:
        """pkg-a is released and in pkg-c's build-system.requires. Download it."""
        with diny.provide():
            plan = get_plan_json("--dev")
        downloads = _commands_of_type(plan, "build", "download_wheels")
        tags = [d["tag_name"] for d in downloads]
        assert "pkg-a/v1.0.0" in tags

    def test_released_build_dep_downloaded_to_deps(
        self, build_requires_workspace: Path
    ) -> None:
        """Released build deps go to deps/, same as released runtime deps."""
        with diny.provide():
            plan = get_plan_json("--dev")
        downloads = _commands_of_type(plan, "build", "download_wheels")
        pkg_a_dl = next(d for d in downloads if "pkg-a" in d["tag_name"])
        assert pkg_a_dl["output_dir"] == "deps"

    def test_packages_flag_excludes_build_only_dep_from_targets(
        self, build_requires_workspace: Path
    ) -> None:
        """--packages pkg-b pkg-c excludes pkg-d from targets."""
        with diny.provide():
            plan = get_plan_json("--dev", "--packages", "pkg-b", "pkg-c")
        releases = _commands_of_type(plan, "release", "create_release")
        titles = [r["title"] for r in releases]
        assert not any("pkg-d" in t for t in titles)

    def test_excluded_build_dep_discovered_as_needs_build(
        self, build_requires_workspace: Path
    ) -> None:
        """When pkg-d is excluded from targets, it's still built as a dep."""
        with diny.provide():
            plan = get_plan_json("--dev", "--packages", "pkg-b", "pkg-c")
        builds = _commands_of_type(plan, "build", "build")
        assert any("pkg-d" in b["label"] for b in builds)

    def test_excluded_build_dep_goes_to_deps_dir(
        self, build_requires_workspace: Path
    ) -> None:
        """When pkg-d is not a target, its wheel goes to deps/."""
        with diny.provide():
            plan = get_plan_json("--dev", "--packages", "pkg-b", "pkg-c")
        builds = _commands_of_type(plan, "build", "build")
        pkg_d_build = next(b for b in builds if "pkg-d" in b["label"])
        assert pkg_d_build["out_dir"] == "deps"

    def test_excluded_build_dep_still_ordered_first(
        self, build_requires_workspace: Path
    ) -> None:
        """Even when excluded from targets, pkg-d builds before pkg-c."""
        with diny.provide():
            plan = get_plan_json("--dev", "--packages", "pkg-b", "pkg-c")
        builds = _commands_of_type(plan, "build", "build")
        labels = [b["label"] for b in builds]
        assert labels.index("Build pkg-d") < labels.index("Build pkg-c")


class TestReleaseJobStructure:
    """Verify release job downloads artifacts and attaches wheels."""

    def test_no_artifact_download_for_local(self, released_workspace: Path) -> None:
        """Local release skips artifact download (wheels already in dist/)."""
        with diny.provide():
            plan = get_plan_json("--dev")
        downloads = _commands_of_type(plan, "release", "download_run_artifacts")
        assert len(downloads) == 0

    def test_creates_tags_for_each_package(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        tags = _commands_of_type(plan, "release", "create_tag")
        tag_names = {t["tag_name"] for t in tags}
        assert any("pkg-b" in t for t in tag_names)
        assert any("pkg-c" in t for t in tag_names)
        # pkg-a is not being released.
        assert not any("pkg-a" in t for t in tag_names)

    def test_creates_github_releases_with_wheel_globs(
        self, released_workspace: Path
    ) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        releases = _commands_of_type(plan, "release", "create_release")
        for rel in releases:
            assert rel["files"], f"No files for {rel['title']}"
            assert any(".whl" in f for f in rel["files"])

    def test_latest_package_marked(self, released_workspace: Path) -> None:
        """pkg-c is configured as latest in [tool.uvr.config]."""
        with diny.provide():
            plan = get_plan_json("--dev")
        releases = _commands_of_type(plan, "release", "create_release")
        latest = [r for r in releases if r["make_latest"]]
        non_latest = [r for r in releases if not r["make_latest"]]
        assert len(latest) == 1
        assert "pkg-c" in latest[0]["title"]
        assert len(non_latest) >= 1


class TestPublishJobStructure:
    """Verify publish job downloads from GitHub release then publishes."""

    def test_no_wheel_download_for_local(self, released_workspace: Path) -> None:
        """Local release skips wheel download (wheels already in dist/)."""
        with diny.provide():
            plan = get_plan_json("--dev")
        downloads = _commands_of_type(plan, "publish", "download_wheels")
        assert len(downloads) == 0

    def test_publishes_each_package(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        publishes = _commands_of_type(plan, "publish", "publish_to_index")
        names = {p["package_name"] for p in publishes}
        assert "pkg-b" in names
        assert "pkg-c" in names

    def test_publish_uses_configured_index(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        publishes = _commands_of_type(plan, "publish", "publish_to_index")
        for p in publishes:
            assert p["index"] == "pypi"

    def test_ci_downloads_all_platforms(self, released_workspace: Path) -> None:
        """CI publish must download every platform's wheel.

        DownloadWheelsCommand defaults to filtering wheels to the host
        runner's tag set, which would strip every wheel built on a different
        platform and leave PyPI with a single-platform release.
        """
        with diny.provide():
            plan = get_plan_json("--dev", where="ci")
        downloads = _commands_of_type(plan, "publish", "download_wheels")
        assert downloads, "publish job should download wheels in CI mode"
        for cmd in downloads:
            assert cmd["all_platforms"] is True, (
                f"publish download {cmd['tag_name']} must keep all platforms"
            )


class TestBumpJobStructure:
    """Verify post-release bump job structure."""

    def test_bumps_each_released_package(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        versions = _commands_of_type(plan, "bump", "set_version")
        names = {v["label"] for v in versions}
        assert any("pkg-b" in n for n in names)
        assert any("pkg-c" in n for n in names)

    def test_bump_uses_actual_package_path(self, released_workspace: Path) -> None:
        """Bump commands must use the real workspace path, not packages/{name}."""
        with diny.provide():
            plan = get_plan_json("--dev")
        versions = _commands_of_type(plan, "bump", "set_version")
        for cmd in versions:
            # Every package_path must point to a directory that exists.
            assert (released_workspace / cmd["package_path"]).exists(), (
                f"package_path {cmd['package_path']!r} does not exist"
            )

    def test_creates_baseline_tags(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        tags = _commands_of_type(plan, "bump", "create_tag")
        assert len(tags) >= 1
        assert all("-base" in t["tag_name"] for t in tags)

    def test_commits_and_pushes(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        commits = _commands_of_type(plan, "bump", "commit")
        pushes = _commands_of_type(plan, "bump", "push")
        assert len(commits) == 1
        assert len(pushes) == 1

    def test_syncs_lockfile(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        syncs = _commands_of_type(plan, "bump", "sync_lockfile")
        assert len(syncs) == 1


class TestPlanMetadata:
    """Verify plan-level metadata from the workspace config."""

    def test_build_matrix(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        assert plan["build_matrix"] == [["ubuntu-latest"]]

    def test_python_version(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        assert plan["python_version"] == "3.12"

    def test_publish_environment(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        assert plan["publish_environment"] == "release"

    def test_validate_not_skipped(self, released_workspace: Path) -> None:
        """Validate is never auto-skipped even though it has no uvr commands."""
        with diny.provide():
            plan = get_plan_json("--dev")
        assert "validate" not in plan["skip"]


class TestChangeDetection:
    """Verify change detection with tagged vs untagged packages."""

    def test_all_untagged_shows_initial_release(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with diny.provide():
            run_cli("status")
        out = capsys.readouterr().out
        assert "initial release" in out
        assert "pkg-a" in out and "pkg-b" in out

    def test_tagged_package_not_changed(
        self, released_workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pkg-a is tagged. It should not appear as changed."""
        with diny.provide():
            run_cli("status")
        out = capsys.readouterr().out
        # Table rows: STATUS PACKAGE VERSION DIFF_FROM
        # pkg-a should be "unchanged", pkg-b and pkg-c should not be.
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        pkg_a_line = next(line for line in lines if "pkg-a" in line)
        assert "unchanged" in pkg_a_line
        pkg_b_line = next(line for line in lines if "pkg-b" in line)
        assert "unchanged" not in pkg_b_line
        pkg_c_line = next(line for line in lines if "pkg-c" in line)
        assert "unchanged" not in pkg_c_line

    def test_dep_propagation(
        self, released_workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """pkg-c depends on pkg-b. If pkg-b changed, pkg-c should too."""
        with diny.provide():
            run_cli("status")
        out = capsys.readouterr().out
        assert "pkg-c" in out
        # pkg-c changes because pkg-b changed (dependency propagation)
        # or because it's an initial release. Either way, it's dirty.

    def test_no_changes_after_full_tag(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from conftest import tag_all

        tag_all(workspace)
        with diny.provide():
            run_cli("status")
        assert "Nothing changed since last release" in capsys.readouterr().out

    def test_change_after_file_edit(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from conftest import tag_all

        tag_all(workspace)
        # Edit a file in pkg-a after tagging.
        (workspace / "packages" / "pkg-a" / "pkg_a" / "__init__.py").write_text(
            "# changed"
        )
        git(workspace, "add", ".")
        git(workspace, "commit", "-m", "edit pkg-a")
        with diny.provide():
            run_cli("status")
        out = capsys.readouterr().out
        assert "pkg-a" in out and "files changed" in out
        # pkg-b depends on pkg-a, should propagate.
        assert "pkg-b" in out and "dependency changed" in out


class TestJobsSubcommand:
    """Test uvr jobs <name> with a serialized plan."""

    def test_jobs_validate_exits_clean(
        self, released_workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        monkeypatch.setenv("UVR_PLAN", json.dumps(plan))
        with diny.provide():
            run_cli("jobs", "validate")

    def test_jobs_unknown_name_errors(
        self,
        released_workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        monkeypatch.setenv("UVR_PLAN", json.dumps(plan))
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("jobs", "nonexistent")
        assert "not found" in capsys.readouterr().err

    def test_jobs_no_env_var_errors(
        self,
        released_workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("UVR_PLAN", raising=False)
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("jobs", "build")
        assert "UVR_PLAN" in capsys.readouterr().err


class TestJsonOutput:
    """Test --json flag produces valid parseable plan."""

    def test_json_output_is_valid(self, released_workspace: Path) -> None:
        with diny.provide():
            plan = get_plan_json("--dev")
        assert "jobs" in plan
        assert "build_matrix" in plan
        job_names = [j["name"] for j in plan["jobs"]]
        assert "build" in job_names
        assert "release" in job_names
        assert "publish" in job_names
        assert "bump" in job_names


class TestBumpFlags:
    """Test --force and --no-pin on bump."""

    def test_force_bumps_even_after_tagging(self, workspace: Path) -> None:
        from conftest import tag_all

        tag_all(workspace)
        # Without --force/--all-packages, nothing to bump.
        with diny.provide():
            run_cli("version", "--bump", "minor", "--no-commit", "--no-push", "--force")
        a = read_toml(workspace / "packages" / "pkg-a" / "pyproject.toml")
        assert a["project"]["version"] == "0.2.0.dev0"

    def test_no_pin_skips_dep_pinning(self, workspace: Path) -> None:
        with diny.provide():
            run_cli(
                "version", "--bump", "minor", "--no-commit", "--no-push", "--no-pin"
            )
        b = read_toml(workspace / "packages" / "pkg-b" / "pyproject.toml")
        deps = b["project"]["dependencies"]
        # Original dep should be unchanged (not pinned to new version).
        assert deps == ["pkg-a>=0.1.0"]


class TestStripDev:
    """Test the .devN stripping flow."""

    def test_non_dev_release_from_dev_shows_strip_commands(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("release", "--dry-run", "--where", "local")
        err = capsys.readouterr().err
        assert "Dev versions need .devN stripped" in err

    def test_dev_release_skips_strip_dev(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with diny.provide():
            run_cli("release", "--dry-run", "--where", "local", "--dev")
        out = capsys.readouterr().out
        assert "Pipeline" in out


class TestLocalRelease:
    """Test --where local executes commands directly (no CI dispatch)."""

    def test_local_release_builds_and_tags(
        self,
        workspace: Path,
        mock_builds: list[list[str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mock external commands, run local release, verify it executes."""
        _real = subprocess.run

        created_tags: list[str] = []

        def _patched(args: str | list[str], **kwargs):
            if not isinstance(args, list):
                return _real(args, **kwargs)
            # Mock git tag (skip -l checks, only track creates).
            # Annotated tag form: ["git", "tag", "-a", "-m", <name>, <name>].
            if len(args) >= 3 and args[0] == "git" and args[1] == "tag":
                if args[2] == "-l":
                    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
                created_tags.append(args[-1])
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            # Mock git push, pull, config, status
            if (
                len(args) >= 2
                and args[0] == "git"
                and args[1] in ("push", "pull", "config", "status")
            ):
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            # Mock gh release (view returns 1 = not found, create returns 0)
            if len(args) >= 3 and args[0] == "gh" and args[1] == "release":
                if args[2] == "view":
                    return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            # Mock gh run download
            if len(args) >= 3 and args[0] == "gh" and args[1] == "run":
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            # Mock all uv commands (build, publish, sync)
            if len(args) >= 2 and args[0] == "uv":
                if args[1] == "build":
                    mock_builds.append(list(args))
                return subprocess.CompletedProcess(args, 0)
            return _real(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", _patched)
        monkeypatch.setenv("RUN_ID", "12345")

        with diny.provide():
            run_cli("release", "--where", "local", "--dev", "-y")

        assert len(mock_builds) >= 1
        assert any("pkg-a" in t or "pkg-b" in t for t in created_tags)


class TestMultiRunnerMatrix:
    """Verify build_matrix computation from [tool.uvr.runners]."""

    def test_default_is_ubuntu(self, released_workspace: Path) -> None:
        """No runners config defaults to [["ubuntu-latest"]]."""
        with diny.provide():
            plan = get_plan_json("--dev")
        assert plan["build_matrix"] == [["ubuntu-latest"]]

    def test_single_package_custom_runner(self, released_workspace: Path) -> None:
        """One package with a custom runner, others default to ubuntu."""
        _set_runners(released_workspace, {"pkg-b": [["macos-latest"]]})
        with diny.provide():
            plan = get_plan_json("--dev")
        matrix = plan["build_matrix"]
        assert ["macos-latest"] in matrix
        assert ["ubuntu-latest"] in matrix

    def test_multi_runner_per_package(self, released_workspace: Path) -> None:
        """One package building on two different runners."""
        _set_runners(
            released_workspace,
            {"pkg-b": [["ubuntu-latest"], ["macos-latest"]]},
        )
        with diny.provide():
            plan = get_plan_json("--dev")
        matrix = plan["build_matrix"]
        assert ["ubuntu-latest"] in matrix
        assert ["macos-latest"] in matrix

    def test_multi_label_runner(self, released_workspace: Path) -> None:
        """Compound runner label like [self-hosted, linux, x64]."""
        _set_runners(
            released_workspace,
            {"pkg-b": [["self-hosted", "linux", "x64"]]},
        )
        with diny.provide():
            plan = get_plan_json("--dev")
        matrix = plan["build_matrix"]
        assert ["self-hosted", "linux", "x64"] in matrix

    def test_deduplication(self, released_workspace: Path) -> None:
        """Same runner on two packages appears once in the matrix."""
        _set_runners(
            released_workspace,
            {
                "pkg-b": [["ubuntu-latest"]],
                "pkg-c": [["ubuntu-latest"]],
            },
        )
        with diny.provide():
            plan = get_plan_json("--dev")
        assert plan["build_matrix"] == [["ubuntu-latest"]]

    def test_different_runners_per_package(self, released_workspace: Path) -> None:
        """Different runners on different packages both appear in the matrix."""
        _set_runners(
            released_workspace,
            {
                "pkg-b": [["macos-latest"]],
                "pkg-c": [["self-hosted", "arm64"]],
            },
        )
        with diny.provide():
            plan = get_plan_json("--dev")
        matrix = plan["build_matrix"]
        assert ["macos-latest"] in matrix
        assert ["self-hosted", "arm64"] in matrix
        assert len(matrix) == 2

    def test_dedup_ignores_label_order(self, released_workspace: Path) -> None:
        """["linux", "x64"] and ["x64", "linux"] are the same runner set."""
        _set_runners(
            released_workspace,
            {
                "pkg-b": [["linux", "x64"]],
                "pkg-c": [["x64", "linux"]],
            },
        )
        with diny.provide():
            plan = get_plan_json("--dev")
        # Both sort to ("linux", "x64") so only one entry.
        assert len(plan["build_matrix"]) == 1


class TestRunnerAwareBuild:
    """Verify build commands carry runner labels and filter by UVR_RUNNER."""

    def test_build_commands_carry_runners(self, released_workspace: Path) -> None:
        """Each BuildCommand includes effective runners (own + inherited)."""
        _set_runners(
            released_workspace,
            {
                "pkg-b": [["ubuntu-latest"]],
                "pkg-c": [["ubuntu-latest"], ["macos-latest"]],
            },
        )
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        pkg_b = next(b for b in builds if "pkg-b" in b["label"])
        pkg_c = next(b for b in builds if "pkg-c" in b["label"])
        # pkg-b inherits macos-latest from pkg-c (which depends on pkg-b).
        assert ["ubuntu-latest"] in pkg_b["runners"]
        assert ["macos-latest"] in pkg_b["runners"]
        assert pkg_c["runners"] == [["macos-latest"], ["ubuntu-latest"]]

    def test_default_runners_for_targets(self, released_workspace: Path) -> None:
        """Targets without explicit runners default to ubuntu-latest."""
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        for b in builds:
            assert b["runners"] == [["ubuntu-latest"]]

    def test_build_command_skips_wrong_runner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BuildCommand.execute() returns 0 without building on wrong runner."""
        from uv_release.commands import BuildCommand

        cmd = BuildCommand(
            label="Build pkg-a",
            package_path="packages/pkg-a",
            runners=[["macos-latest"]],
        )
        monkeypatch.setenv("UVR_RUNNER", '["ubuntu-latest"]')
        assert cmd.execute() == 0

    def test_build_command_runs_on_matching_runner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BuildCommand.execute() runs on a matching runner."""
        from unittest.mock import patch

        from uv_release.commands import BuildCommand

        cmd = BuildCommand(
            label="Build pkg-a",
            package_path="packages/pkg-a",
            runners=[["ubuntu-latest"], ["macos-latest"]],
        )
        monkeypatch.setenv("UVR_RUNNER", '["macos-latest"]')
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            rc = cmd.execute()
        assert rc == 0
        assert mock_run.called

    def test_build_command_runs_without_uvr_runner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BuildCommand.execute() runs when UVR_RUNNER is not set."""
        from unittest.mock import patch

        from uv_release.commands import BuildCommand

        cmd = BuildCommand(
            label="Build pkg-a",
            package_path="packages/pkg-a",
            runners=[["macos-latest"]],
        )
        monkeypatch.delenv("UVR_RUNNER", raising=False)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            rc = cmd.execute()
        assert rc == 0
        assert mock_run.called

    def test_build_command_runs_with_empty_runners(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BuildCommand with no runners assigned runs on any runner."""
        from unittest.mock import patch

        from uv_release.commands import BuildCommand

        cmd = BuildCommand(
            label="Build pkg-a",
            package_path="packages/pkg-a",
            runners=[],
        )
        monkeypatch.setenv("UVR_RUNNER", '["some-runner"]')
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            rc = cmd.execute()
        assert rc == 0
        assert mock_run.called

    def test_dep_inherits_runners_from_dependent(
        self, released_workspace: Path
    ) -> None:
        """pkg-b inherits macos runner from pkg-c because pkg-c depends on pkg-b."""
        _set_runners(
            released_workspace,
            {
                "pkg-b": [["ubuntu-latest"]],
                "pkg-c": [["macos-latest"]],
            },
        )
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        pkg_b = next(b for b in builds if "pkg-b" in b["label"])
        assert ["macos-latest"] in pkg_b["runners"]
        assert ["ubuntu-latest"] in pkg_b["runners"]

    def test_target_runners_only_own(self, released_workspace: Path) -> None:
        """target_runners only includes the package's own runners, not inherited."""
        _set_runners(
            released_workspace,
            {
                "pkg-b": [["ubuntu-latest"]],
                "pkg-c": [["macos-latest"]],
            },
        )
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        pkg_b = next(b for b in builds if "pkg-b" in b["label"])
        assert pkg_b["target_runners"] == [["ubuntu-latest"]]

    def test_out_dir_deps_on_inherited_runner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """On an inherited runner, BuildCommand outputs to deps/ not dist/."""
        from uv_release.commands import BuildCommand

        cmd = BuildCommand(
            label="Build pkg-b",
            package_path="packages/pkg-b",
            out_dir="dist",
            runners=[["ubuntu-latest"], ["macos-latest"]],
            target_runners=[["ubuntu-latest"]],
        )
        monkeypatch.setenv("UVR_RUNNER", '["macos-latest"]')
        assert cmd._effective_out_dir() == "deps"

    def test_out_dir_dist_on_own_runner(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """On the package's own runner, BuildCommand outputs to dist/."""
        from uv_release.commands import BuildCommand

        cmd = BuildCommand(
            label="Build pkg-b",
            package_path="packages/pkg-b",
            out_dir="dist",
            runners=[["ubuntu-latest"], ["macos-latest"]],
            target_runners=[["ubuntu-latest"]],
        )
        monkeypatch.setenv("UVR_RUNNER", '["ubuntu-latest"]')
        assert cmd._effective_out_dir() == "dist"

    def test_build_order_preserved_with_runners(self, released_workspace: Path) -> None:
        """Topo ordering still correct when packages have different runners."""
        _set_runners(
            released_workspace,
            {
                "pkg-b": [["ubuntu-latest"]],
                "pkg-c": [["macos-latest"]],
            },
        )
        with diny.provide():
            plan = get_plan_json("--dev")
        builds = _commands_of_type(plan, "build", "build")
        labels = [b["label"] for b in builds]
        assert labels.index("Build pkg-b") < labels.index("Build pkg-c")


class TestSkipAndSkipTo:
    """Verify --skip and --skip-to flags produce correct plan.skip lists."""

    def test_skip_build(self, released_workspace: Path) -> None:
        """--skip build empties the build job and adds it to plan.skip."""
        with diny.provide():
            plan = get_plan_json("--dev", "--skip", "build")
        assert "build" in plan["skip"]
        build_job = _job(plan, "build")
        assert build_job["commands"] == []

    def test_skip_release(self, released_workspace: Path) -> None:
        """--skip release empties the release job but build still has commands."""
        with diny.provide():
            plan = get_plan_json("--dev", "--skip", "release")
        assert "release" in plan["skip"]
        release_job = _job(plan, "release")
        assert release_job["commands"] == []
        build_job = _job(plan, "build")
        assert len(build_job["commands"]) > 0

    def test_skip_multiple(self, released_workspace: Path) -> None:
        """--skip build release skips both."""
        with diny.provide():
            plan = get_plan_json("--dev", "--skip", "build", "release")
        assert "build" in plan["skip"]
        assert "release" in plan["skip"]

    def test_skip_to_release(self, released_workspace: Path) -> None:
        """--skip-to release skips build but not validate or release."""
        _add_workflow(released_workspace, _WORKFLOW_CORE_ONLY)
        with diny.provide():
            plan = get_plan_json("--dev", "--skip-to", "release")
        assert "build" in plan["skip"]
        assert "release" not in plan["skip"]

    def test_skip_to_publish(self, released_workspace: Path) -> None:
        """--skip-to publish skips build and release."""
        _add_workflow(released_workspace, _WORKFLOW_CORE_ONLY)
        with diny.provide():
            plan = get_plan_json("--dev", "--skip-to", "publish")
        assert "build" in plan["skip"]
        assert "release" in plan["skip"]
        assert "publish" not in plan["skip"]

    def test_skip_to_bump(self, released_workspace: Path) -> None:
        """--skip-to bump skips build, release, and publish."""
        _add_workflow(released_workspace, _WORKFLOW_CORE_ONLY)
        with diny.provide():
            plan = get_plan_json("--dev", "--skip-to", "bump")
        assert "build" in plan["skip"]
        assert "release" in plan["skip"]
        assert "publish" in plan["skip"]
        assert "bump" not in plan["skip"]

    def test_validate_not_skipped_by_skip_to(self, released_workspace: Path) -> None:
        """--skip-to bump skips build/release/publish but never validate."""
        _add_workflow(released_workspace, _WORKFLOW_CORE_ONLY)
        with diny.provide():
            plan = get_plan_json("--dev", "--skip-to", "bump")
        assert "validate" not in plan["skip"]
        assert "build" in plan["skip"]

    def test_custom_job_name_passthrough(self, released_workspace: Path) -> None:
        """--skip with a non-core job name passes through to plan.skip for CI."""
        with diny.provide():
            plan = get_plan_json("--dev", "--skip", "checks")
        assert "checks" in plan["skip"]
        # Core jobs unaffected.
        build_job = _job(plan, "build")
        assert len(build_job["commands"]) > 0

    def test_dry_run_shows_skip_status(
        self, released_workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--dry-run output shows (skip) for skipped jobs."""
        with diny.provide():
            run_cli(
                "release", "--dry-run", "--where", "local", "--dev", "--skip", "build"
            )
        out = capsys.readouterr().out
        assert "build: (skip)" in out
        assert "  release" in out
        # release should not be skipped.
        assert "release: (skip)" not in out

    def test_skip_combined_with_skip_to(self, released_workspace: Path) -> None:
        """--skip-to release --skip publish skips build and publish."""
        _add_workflow(released_workspace, _WORKFLOW_CORE_ONLY)
        with diny.provide():
            plan = get_plan_json("--dev", "--skip-to", "release", "--skip", "publish")
        assert "build" in plan["skip"]
        assert "publish" in plan["skip"]
        assert "release" not in plan["skip"]

    def test_skip_to_with_custom_job_between(self, released_workspace: Path) -> None:
        """--skip-to build also skips custom jobs before build."""
        _add_workflow(released_workspace)
        with diny.provide():
            plan = get_plan_json("--dev", "--skip-to", "build")
        assert "checks" in plan["skip"]
        assert "build" not in plan["skip"]


_WORKFLOW_CORE_ONLY = """\
name: Release Wheels
on:
  workflow_dispatch:
    inputs:
      plan:
        type: string
        required: true
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
    - run: echo validate
  build:
    runs-on: ubuntu-latest
    steps:
    - run: echo build
  release:
    runs-on: ubuntu-latest
    steps:
    - run: echo release
  publish:
    runs-on: ubuntu-latest
    steps:
    - run: echo publish
  bump:
    runs-on: ubuntu-latest
    steps:
    - run: echo bump
"""

_WORKFLOW_WITH_CUSTOM_JOBS = """\
name: Release Wheels
on:
  workflow_dispatch:
    inputs:
      plan:
        type: string
        required: true
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
    - run: echo validate
  checks:
    runs-on: ubuntu-latest
    needs: [validate]
    if: ${{ !contains(fromJSON(inputs.plan).skip, 'checks') }}
    steps:
    - run: uv run poe check
  build:
    runs-on: ubuntu-latest
    needs: [checks]
    steps:
    - run: echo build
  release:
    runs-on: ubuntu-latest
    needs: [build]
    steps:
    - run: echo release
  publish:
    runs-on: ubuntu-latest
    needs: [release]
    steps:
    - run: echo publish
  bump:
    runs-on: ubuntu-latest
    needs: [publish]
    steps:
    - run: echo bump
  notify:
    runs-on: ubuntu-latest
    needs: [bump]
    if: ${{ !contains(fromJSON(inputs.plan).skip, 'notify') }}
    steps:
    - run: echo notify
"""


def _add_workflow(root: Path, content: str = _WORKFLOW_WITH_CUSTOM_JOBS) -> None:
    """Write a release.yml workflow file into the workspace."""
    wf_dir = root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "release.yml").write_text(content)
    git(root, "add", ".")
    git(root, "commit", "-m", "add workflow")


class TestCustomJobsDisplay:
    """Verify custom jobs from release.yml appear in dry-run output."""

    def test_custom_jobs_shown_in_dry_run(
        self, released_workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Custom jobs from the workflow YAML appear in the plan printout."""
        _add_workflow(released_workspace)
        with diny.provide():
            run_cli("release", "--dry-run", "--where", "local", "--dev")
        out = capsys.readouterr().out
        assert "  checks" in out
        assert "  notify" in out

    def test_jobs_interleaved_in_workflow_order(
        self, released_workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Jobs print in workflow YAML order: checks between validate and build."""
        _add_workflow(released_workspace)
        with diny.provide():
            run_cli("release", "--dry-run", "--where", "local", "--dev")
        out = capsys.readouterr().out
        lines = [
            line.strip()
            for line in out.splitlines()
            if line.strip().startswith(
                ("validate", "checks", "build", "release", "publish", "bump", "notify")
            )
        ]
        names = [line.split(":")[0] for line in lines]
        # Workflow order: validate, checks, build, release, publish, bump, notify
        assert names.index("checks") < names.index("build")
        assert names.index("checks") > names.index("validate")
        assert names.index("notify") > names.index("bump")

    def test_skipped_custom_job_shows_skip(
        self, released_workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--skip checks shows the custom job as (skip)."""
        _add_workflow(released_workspace)
        with diny.provide():
            run_cli(
                "release",
                "--dry-run",
                "--where",
                "local",
                "--dev",
                "--skip",
                "checks",
            )
        out = capsys.readouterr().out
        assert "checks: (skip)" in out
        # notify is not skipped.
        assert "notify: (skip)" not in out

    def test_only_workflow_jobs_shown(
        self, released_workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Only jobs from the workflow YAML appear in the printout."""
        with diny.provide():
            run_cli("release", "--dry-run", "--where", "local", "--dev")
        out = capsys.readouterr().out
        assert "  build" in out
        # No custom jobs in the default fixture workflow.
        assert "checks" not in out
