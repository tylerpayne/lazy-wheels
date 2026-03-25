"""Tests for uv_release_monorepo.cli."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.cli import (
    __version__,
    _discover_packages,
    _find_latest_release_tag,
    _parse_install_spec,
    _read_matrix,
    cli,
    cmd_init,
    cmd_install,
    cmd_release,
    cmd_run,
    cmd_status,
)
from uv_release_monorepo.models import MatrixEntry, PackageInfo, ReleasePlan


def _write_workspace_repo(root: Path, package_names: list[str]) -> None:
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
    )
    for package_name in package_names:
        package_dir = root / "packages" / package_name
        package_dir.mkdir(parents=True)
        (package_dir / "pyproject.toml").write_text(
            f'[project]\nname = "{package_name}"\nversion = "1.0.0"\n'
        )


def _make_plan(
    changed: list[str] | None = None, unchanged: list[str] | None = None
) -> ReleasePlan:
    """Helper to create a ReleasePlan for testing."""
    changed = changed or []
    unchanged = unchanged or []
    all_pkgs = changed + unchanged
    packages = {
        name: PackageInfo(path=f"packages/{name}", version="1.0.0", deps=[])
        for name in all_pkgs
    }
    return ReleasePlan(
        uvr_version=__version__,
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
    )


class TestInit:
    """Tests for init command."""

    def test_writes_default_release_workflow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init writes the executor workflow template."""
        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            workflow_dir=".github/workflows",
            matrix=None,
        )
        cmd_init(args)

        workflow = tmp_path / ".github" / "workflows" / "release.yml"
        assert workflow.exists()
        assert "jobs:\n  build:" in workflow.read_text()

    def test_matrix_writes_split_jobs_workflow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init with matrix args creates executor workflow and writes matrix to pyproject.toml."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            workflow_dir=".github/workflows",
            matrix=[
                ["pkg-alpha", "ubuntu-latest"],
                ["pkg-beta", "ubuntu-latest", "ubuntu-24.04-arm"],
            ],
        )
        cmd_init(args)

        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "jobs:\n  build:" in workflow
        # Matrix is stored in pyproject.toml, not in the workflow comment
        pyproject_text = (tmp_path / "pyproject.toml").read_text()
        assert "pkg-beta" in pyproject_text
        assert "ubuntu-24.04-arm" in pyproject_text


@patch("uv_release_monorepo.cli.run_pipeline")
def test_run_command_uses_workflow_steps_runner(mock_run_pipeline: MagicMock) -> None:
    """run command dispatches through workflow_steps.run_pipeline."""
    args = argparse.Namespace(rebuild_all=True, no_push=False, dry_run=False, plan=None)
    cmd_run(args)

    mock_run_pipeline.assert_called_once_with(rebuild_all=True, push=True, dry_run=False)


@patch("uv_release_monorepo.cli.run_pipeline")
def test_run_command_no_push_flag(mock_run_pipeline: MagicMock) -> None:
    """run command passes push=False when --no-push is set."""
    args = argparse.Namespace(rebuild_all=False, no_push=True, dry_run=False, plan=None)
    cmd_run(args)

    mock_run_pipeline.assert_called_once_with(
        rebuild_all=False, push=False, dry_run=False
    )


@patch("uv_release_monorepo.cli.run_pipeline")
def test_run_command_dry_run_flag(mock_run_pipeline: MagicMock) -> None:
    """run command passes dry_run=True when --dry-run is set."""
    args = argparse.Namespace(rebuild_all=False, no_push=False, dry_run=True, plan=None)
    cmd_run(args)

    mock_run_pipeline.assert_called_once_with(rebuild_all=False, push=True, dry_run=True)


def test_cli_dry_run_is_valid_arg() -> None:
    """--dry-run is a recognized argument for the run subcommand."""
    with patch.object(sys, "argv", ["uvr", "run", "--dry-run"]):
        with patch("uv_release_monorepo.cli.cmd_run") as mock_run:
            cli()
            args = mock_run.call_args[0][0]
            assert args.dry_run is True


def test_init_workflow_has_uvr_version_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generated workflow has uvr_version input (no baked-in version)."""
    _write_workspace_repo(tmp_path, [])
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(workflow_dir=".github/workflows", matrix=None)
    cmd_init(args)

    workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
    assert "uvr_version" in workflow
    assert "uv-release-monorepo=={0}" in workflow
    assert "__UVR_VERSION__" not in workflow


def test_cli_parses_matrix_args() -> None:
    """CLI correctly parses -m arguments with nargs='+'."""
    with patch.object(
        sys,
        "argv",
        [
            "uvr",
            "init",
            "-m",
            "pkg-alpha",
            "ubuntu-latest",
            "-m",
            "pkg-beta",
            "ubuntu-latest",
            "macos-14",
        ],
    ):
        with patch("uv_release_monorepo.cli.cmd_init") as mock_init:
            cli()
            args = mock_init.call_args[0][0]
            assert args.matrix == [
                ["pkg-alpha", "ubuntu-latest"],
                ["pkg-beta", "ubuntu-latest", "macos-14"],
            ]


class TestInitAdditive:
    """Tests for additive init behavior."""

    def test_init_m_merges_with_existing_matrix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adding a new package preserves existing packages."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        # First init: pkg-alpha
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-alpha", "ubuntu-latest"]],
            )
        )

        # Second init: pkg-beta (should keep pkg-alpha)
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-beta", "ubuntu-latest"]],
            )
        )

        # Both packages should appear in pyproject.toml [tool.uvr.matrix]
        pyproject_text = (tmp_path / "pyproject.toml").read_text()
        assert "pkg-alpha" in pyproject_text
        assert "pkg-beta" in pyproject_text

    def test_init_m_replaces_runners_for_existing_package(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Re-specifying a package replaces its runner list."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        # First init: ubuntu-latest
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-alpha", "ubuntu-latest"]],
            )
        )

        # Second init: replace with macos-14
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-alpha", "macos-14"]],
            )
        )

        # Check pyproject.toml has the updated runner for pkg-alpha
        result = _read_matrix(tmp_path)
        assert result["pkg-alpha"] == ["macos-14"]

    def test_init_no_m_preserves_existing_matrix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bare `uvr init` on a matrix workflow preserves matrix entries."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        # First init with matrix
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-alpha", "ubuntu-latest", "macos-14"]],
            )
        )

        # Second init without -m
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=None,
            )
        )

        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "jobs:\n  build:" in workflow
        # Matrix is preserved in pyproject.toml
        pyproject_text = (tmp_path / "pyproject.toml").read_text()
        assert "pkg-alpha" in pyproject_text
        assert "ubuntu-latest" in pyproject_text
        assert "macos-14" in pyproject_text

    def test_init_m_upgrades_simple_to_matrix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adding -m always uses executor template (which has build job)."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        # First init: simple workflow (executor template always has build job)
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=None,
            )
        )
        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "jobs:\n  build:" in workflow

        # Second init: add matrix
        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[["pkg-alpha", "ubuntu-latest"]],
            )
        )
        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "jobs:\n  build:" in workflow
        # Matrix is stored in pyproject.toml
        pyproject_text = (tmp_path / "pyproject.toml").read_text()
        assert "pkg-alpha" in pyproject_text


class TestReadMatrix:
    """Tests for _read_matrix()."""

    def test_returns_empty_when_no_matrix(self, tmp_path: Path) -> None:
        """Returns {} for a repo with no [tool.uvr.matrix]."""
        _write_workspace_repo(tmp_path, [])
        result = _read_matrix(tmp_path)
        assert result == {}

    def test_returns_empty_when_no_pyproject(self, tmp_path: Path) -> None:
        """Returns {} when pyproject.toml does not exist."""
        result = _read_matrix(tmp_path)
        assert result == {}

    def test_returns_matrix_after_cmd_init(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns the matrix after cmd_init has been run with -m args."""
        _write_workspace_repo(tmp_path, ["pkg-a", "pkg-b"])
        monkeypatch.chdir(tmp_path)

        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[
                    ["pkg-a", "ubuntu-latest"],
                    ["pkg-b", "ubuntu-latest", "macos-14"],
                ],
            )
        )

        result = _read_matrix(tmp_path)
        assert result == {
            "pkg-a": ["ubuntu-latest"],
            "pkg-b": ["ubuntu-latest", "macos-14"],
        }


class TestStatus:
    """Tests for status command."""

    def test_status_shows_matrix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        cmd_init(
            argparse.Namespace(
                workflow_dir=".github/workflows",
                matrix=[
                    ["pkg-alpha", "ubuntu-latest"],
                    ["pkg-beta", "ubuntu-latest", "macos-14"],
                ],
            )
        )
        capsys.readouterr()  # clear init output

        cmd_status(argparse.Namespace(workflow_dir=".github/workflows"))
        output = capsys.readouterr().out

        assert "Build matrix:" in output
        assert "pkg-alpha" in output
        assert "pkg-beta" in output
        assert "ubuntu-latest" in output
        assert "macos-14" in output

    def test_status_no_workflow(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)

        cmd_status(argparse.Namespace(workflow_dir=".github/workflows"))
        output = capsys.readouterr().out

        assert "No release workflow found" in output
        assert "uvr init" in output

    def test_status_simple_workflow_shows_packages(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Simple workflow status discovers packages and shows them on ubuntu-latest."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows", matrix=None))
        capsys.readouterr()

        cmd_status(argparse.Namespace(workflow_dir=".github/workflows"))
        output = capsys.readouterr().out

        assert "Build matrix:" in output
        assert "pkg-alpha" in output
        assert "pkg-beta" in output
        assert "ubuntu-latest" in output


class TestDiscoverPackages:
    """Tests for _discover_packages()."""

    def test_discovers_names_and_deps(self, tmp_path: Path) -> None:
        """Discovers packages and resolves internal dependencies."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        beta_toml = tmp_path / "packages" / "pkg-beta" / "pyproject.toml"
        beta_toml.write_text(
            '[project]\nname = "pkg-beta"\nversion = "1.0.0"\n'
            'dependencies = ["pkg-alpha>=1.0"]\n'
        )

        result = _discover_packages(root=tmp_path)

        assert "pkg-alpha" in result
        assert "pkg-beta" in result
        assert result["pkg-alpha"] == ("1.0.0", [])
        assert result["pkg-beta"] == ("1.0.0", ["pkg-alpha"])

    def test_discovers_packages_with_explicit_root(self, tmp_path: Path) -> None:
        """_discover_packages accepts an explicit root parameter."""
        _write_workspace_repo(tmp_path, ["pkg-x"])

        result = _discover_packages(root=tmp_path)

        assert "pkg-x" in result

    def test_status_shows_dependency_matrix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Status command shows dependency matrix."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        beta_toml = tmp_path / "packages" / "pkg-beta" / "pyproject.toml"
        beta_toml.write_text(
            '[project]\nname = "pkg-beta"\nversion = "1.0.0"\n'
            'dependencies = ["pkg-alpha>=1.0"]\n'
        )
        monkeypatch.chdir(tmp_path)

        cmd_init(argparse.Namespace(workflow_dir=".github/workflows", matrix=None))
        capsys.readouterr()

        cmd_status(argparse.Namespace(workflow_dir=".github/workflows"))
        output = capsys.readouterr().out

        assert "Dependencies:" in output
        assert "pkg-alpha" in output
        assert "pkg-beta" in output


class TestFindLatestReleaseTag:
    """Tests for _find_latest_release_tag()."""

    def test_returns_highest_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns the tag with the highest semver for the given package."""
        import json
        import subprocess

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(
                [
                    {"tagName": "pkg-alpha/v0.1.0"},
                    {"tagName": "pkg-alpha/v0.1.2"},
                    {"tagName": "pkg-alpha/v0.1.1"},
                    {"tagName": "other-pkg/v9.9.9"},
                ]
            )
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = _find_latest_release_tag("pkg-alpha")

        assert result == "pkg-alpha/v0.1.2"

    def test_excludes_dev_tags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ignores tags ending with -dev."""
        import json
        import subprocess

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(
                [
                    {"tagName": "pkg-alpha/v0.1.0"},
                    {"tagName": "pkg-alpha/v0.1.1-dev"},
                ]
            )
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = _find_latest_release_tag("pkg-alpha")

        assert result == "pkg-alpha/v0.1.0"

    def test_returns_none_when_no_releases(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns None when no releases exist for the package."""
        import json
        import subprocess

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([{"tagName": "other-pkg/v1.0.0"}])
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = _find_latest_release_tag("pkg-alpha")

        assert result is None

    def test_returns_none_on_gh_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when gh command fails."""
        import subprocess

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = _find_latest_release_tag("pkg-alpha")

        assert result is None


class TestCmdInstall:
    """Tests for cmd_install()."""

    def test_installs_package_and_deps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Installs the requested package and its transitive internal deps."""
        import json
        import subprocess

        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        beta_toml = tmp_path / "packages" / "pkg-beta" / "pyproject.toml"
        beta_toml.write_text(
            '[project]\nname = "pkg-beta"\nversion = "1.0.0"\n'
            'dependencies = ["pkg-alpha>=1.0"]\n'
        )
        monkeypatch.chdir(tmp_path)

        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(
                [
                    {"tagName": "pkg-alpha/v1.0.0"},
                    {"tagName": "pkg-beta/v1.0.0"},
                ]
            )
            if "download" in cmd:
                dir_idx = cmd.index("--dir") + 1
                whl_dir = Path(cmd[dir_idx])
                whl_dir.mkdir(parents=True, exist_ok=True)
                # Create fake wheels matching the glob pkg_name-*.whl
                tag_idx = cmd.index("download") + 1
                tag = cmd[tag_idx]  # e.g. "pkg-alpha/v1.0.0"
                pkg_name = tag.split("/v")[0].replace("-", "_")
                ver = tag.split("/v")[1]
                (whl_dir / f"{pkg_name}-{ver}-py3-none-any.whl").write_bytes(b"")
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        args = argparse.Namespace(package="pkg-beta")
        cmd_install(args)

        # Should have called uv pip install with two wheels (alpha + beta)
        install_calls = [c for c in calls if c[:3] == ["uv", "pip", "install"]]
        assert len(install_calls) == 1
        assert len(install_calls[0]) == 5  # uv pip install <alpha.whl> <beta.whl>

    def test_fails_for_unknown_package(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exits with error when package is not in workspace."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(package="nonexistent-pkg")

        with pytest.raises(SystemExit):
            cmd_install(args)

    def test_pinned_version_uses_specific_tag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PACKAGE@VERSION uses that exact release tag."""
        import json
        import subprocess

        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        download_tags: list[str] = []

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([])
            if "download" in cmd:
                tag_idx = cmd.index("download") + 1
                download_tags.append(cmd[tag_idx])
                dir_idx = cmd.index("--dir") + 1
                whl_dir = cmd[dir_idx]
                Path(whl_dir).mkdir(parents=True, exist_ok=True)
                (Path(whl_dir) / "pkg_alpha-0.1.5-py3-none-any.whl").write_bytes(b"")
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        args = argparse.Namespace(package="pkg-alpha@0.1.5")
        cmd_install(args)

        assert "pkg-alpha/v0.1.5" in download_tags


class TestCmdRelease:
    """Tests for cmd_release()."""

    @patch("uv_release_monorepo.cli.build_plan")
    def test_release_exits_early_when_nothing_changed(
        self,
        mock_build_plan: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_release exits early if plan has no changed packages."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        # Create the workflow file so cmd_release doesn't fail on missing workflow
        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "release.yml").write_text("some: yaml\n")

        mock_build_plan.return_value = (
            _make_plan(changed=[], unchanged=["pkg-alpha"]),
            [],
        )

        args = argparse.Namespace(
            rebuild_all=False,
            yes=False,
            workflow_dir=".github/workflows",
            python_version="3.12",
        )
        cmd_release(args)

        output = capsys.readouterr().out
        assert "Nothing changed" in output

    @patch("uv_release_monorepo.cli.build_plan")
    def test_release_prints_plan_json(
        self,
        mock_build_plan: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """cmd_release prints the plan as JSON and prompts before dispatching."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "release.yml").write_text("some: yaml\n")

        plan = _make_plan(changed=["pkg-alpha"])
        mock_build_plan.return_value = plan, []

        # Simulate user declining the prompt
        monkeypatch.setattr("builtins.input", lambda _: "n")

        args = argparse.Namespace(
            rebuild_all=False,
            yes=False,
            workflow_dir=".github/workflows",
            python_version="3.12",
        )
        cmd_release(args)

        output = capsys.readouterr().out
        # Extract just the JSON block (starts at the first '{')
        json_part = output[output.index("{") :]
        parsed = json.loads(json_part)
        assert "changed" in parsed
        assert "pkg-alpha" in parsed["changed"]

    @patch("subprocess.run")
    @patch("uv_release_monorepo.cli.build_plan")
    def test_release_dispatches_with_yes_flag(
        self,
        mock_build_plan: MagicMock,
        mock_subprocess_run: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """cmd_release --yes dispatches via gh without prompting."""
        _write_workspace_repo(tmp_path, ["pkg-alpha"])
        monkeypatch.chdir(tmp_path)

        workflow_dir = tmp_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "release.yml").write_text("some: yaml\n")

        plan = _make_plan(changed=["pkg-alpha"])
        mock_build_plan.return_value = plan, []

        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="[]")

        args = argparse.Namespace(
            rebuild_all=False,
            yes=True,
            workflow_dir=".github/workflows",
            python_version="3.12",
        )
        cmd_release(args)

        # Verify gh workflow run was called with -f plan=...
        calls = [c for c in mock_subprocess_run.call_args_list]
        trigger_call = calls[0][0][0]  # first positional arg of first call
        assert "gh" in trigger_call
        assert "workflow" in trigger_call
        assert "run" in trigger_call
        # Find -f plan= argument
        joined = " ".join(str(a) for a in trigger_call)
        assert "plan=" in joined


class TestParseInstallSpec:
    """Tests for _parse_install_spec()."""

    def test_local_package(self) -> None:
        gh_repo, package, version = _parse_install_spec("pkg-alpha")
        assert gh_repo is None
        assert package == "pkg-alpha"
        assert version is None

    def test_local_package_with_version(self) -> None:
        gh_repo, package, version = _parse_install_spec("pkg-alpha@1.2.3")
        assert gh_repo is None
        assert package == "pkg-alpha"
        assert version == "1.2.3"

    def test_remote_package(self) -> None:
        gh_repo, package, version = _parse_install_spec("acme/my-monorepo/pkg-alpha")
        assert gh_repo == "acme/my-monorepo"
        assert package == "pkg-alpha"
        assert version is None

    def test_remote_package_with_version(self) -> None:
        gh_repo, package, version = _parse_install_spec(
            "acme/my-monorepo/pkg-alpha@2.0.0"
        )
        assert gh_repo == "acme/my-monorepo"
        assert package == "pkg-alpha"
        assert version == "2.0.0"

    def test_invalid_two_part_spec_raises(self) -> None:
        with pytest.raises(SystemExit):
            _parse_install_spec("acme/pkg-alpha")

    def test_invalid_four_part_spec_raises(self) -> None:
        with pytest.raises(SystemExit):
            _parse_install_spec("acme/org/repo/pkg")


class TestFindLatestReleaseTagRemote:
    """Tests for _find_latest_release_tag() with gh_repo parameter."""

    def test_passes_repo_flag_to_gh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gh release list is called with --repo when gh_repo is provided."""
        import json
        import subprocess

        seen_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            seen_cmds.append(list(cmd))
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([{"tagName": "pkg-alpha/v1.0.0"}])
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        _find_latest_release_tag("pkg-alpha", gh_repo="acme/my-monorepo")

        assert "--repo" in seen_cmds[0]
        assert "acme/my-monorepo" in seen_cmds[0]


class TestCmdInstallRemote:
    """Tests for cmd_install() with remote org/repo/package specs."""

    def test_remote_install_passes_repo_to_gh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Remote install passes --repo to gh release list and download."""
        import json
        import subprocess

        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)

        seen_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            seen_cmds.append(list(cmd))
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([{"tagName": "pkg-alpha/v1.0.0"}])
            if "download" in cmd:
                dir_idx = cmd.index("--dir") + 1
                whl_dir = Path(cmd[dir_idx])
                whl_dir.mkdir(parents=True, exist_ok=True)
                (whl_dir / "pkg_alpha-1.0.0-py3-none-any.whl").write_bytes(b"")
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        args = argparse.Namespace(package="acme/my-monorepo/pkg-alpha")
        cmd_install(args)

        repo_cmds = [c for c in seen_cmds if "--repo" in c]
        assert all("acme/my-monorepo" in c for c in repo_cmds)

    def test_remote_install_pinned_version_skips_tag_lookup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Remote install with @version uses the tag directly without listing releases."""
        import subprocess

        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)

        seen_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            seen_cmds.append(list(cmd))
            result = MagicMock()
            result.returncode = 0
            result.stdout = "[]"
            if "download" in cmd:
                dir_idx = cmd.index("--dir") + 1
                whl_dir = Path(cmd[dir_idx])
                whl_dir.mkdir(parents=True, exist_ok=True)
                (whl_dir / "pkg_alpha-0.5.0-py3-none-any.whl").write_bytes(b"")
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        args = argparse.Namespace(package="acme/my-monorepo/pkg-alpha@0.5.0")
        cmd_install(args)

        list_cmds = [c for c in seen_cmds if "list" in c]
        assert len(list_cmds) == 0
        download_cmds = [c for c in seen_cmds if "download" in c]
        assert any("pkg-alpha/v0.5.0" in c for c in download_cmds)


@patch("uv_release_monorepo.cli.execute_plan")
def test_run_with_plan_calls_execute_plan(
    mock_execute_plan: MagicMock,
) -> None:
    """cmd_run --plan calls execute_plan with the parsed plan."""
    plan = _make_plan(changed=["pkg-alpha"])
    plan_json = plan.model_dump_json()

    args = argparse.Namespace(
        plan=plan_json, no_push=False, rebuild_all=False, dry_run=False
    )
    cmd_run(args)

    mock_execute_plan.assert_called_once()
    (called_plan,) = mock_execute_plan.call_args[0]
    assert called_plan.changed == plan.changed
