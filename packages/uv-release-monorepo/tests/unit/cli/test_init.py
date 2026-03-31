"""Tests for the init and upgrade commands."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from uv_release_monorepo.cli import cmd_init, cmd_upgrade

from tests._helpers import _write_workspace_repo


class TestInit:
    """Tests for init command."""

    def test_writes_default_release_workflow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """init writes the release workflow with all jobs."""
        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(workflow_dir=".github/workflows")
        cmd_init(args)

        workflow = tmp_path / ".github" / "workflows" / "release.yml"
        assert workflow.exists()
        text = workflow.read_text()
        assert "uvr-build:" in text
        assert "uvr-release:" in text
        assert "uvr-bump:" in text

    def test_init_workflow_has_plan_input(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Generated workflow has plan input."""
        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(workflow_dir=".github/workflows")
        cmd_init(args)

        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "plan:" in workflow


def _init_and_get_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Scaffold a workspace, init the workflow, and set up workflow_version."""
    import subprocess as _sp

    from uv_release_monorepo.shared.utils.cli import __version__
    from uv_release_monorepo.cli.init import _load_template, _write_base

    _write_workspace_repo(tmp_path, ["pkg-alpha"])
    monkeypatch.chdir(tmp_path)
    _sp.run(["git", "init"], capture_output=True, check=True)
    _sp.run(["git", "add", "-A"], capture_output=True, check=True)
    _sp.run(
        ["git", "commit", "-m", "init"],
        capture_output=True,
        check=True,
        env=_GIT_ENV,
    )

    # Write template, store version, and save merge base
    template_text = _load_template()
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf = wf_dir / "release.yml"
    wf.write_text(template_text)
    _write_base(tmp_path, ".github/workflows/release.yml", template_text)

    # Store workflow_version in pyproject.toml
    pyproject = tmp_path / "pyproject.toml"
    text = pyproject.read_text()
    text += f'\n[tool.uvr.config]\nworkflow_version = "{__version__}"\n'
    pyproject.write_text(text)

    _sp.run(["git", "add", "-A"], capture_output=True, check=True)
    _sp.run(
        ["git", "commit", "-m", "add workflow"],
        capture_output=True,
        check=True,
        env=_GIT_ENV,
    )
    return wf


def _upgrade_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = dict(
        workflow_dir=".github/workflows",
        yes=True,
        upgrade=True,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


_GIT_ENV = {
    **__import__("os").environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}


def _git_commit_wf(wf: Path) -> None:
    """Stage and commit the workflow file so it passes the dirty check."""
    import subprocess as _sp

    _sp.run(["git", "add", str(wf)], capture_output=True, check=True)
    _sp.run(
        ["git", "commit", "-m", "update wf"],
        capture_output=True,
        check=True,
        env=_GIT_ENV,
    )


class TestUpgrade:
    """Tests for uvr workflow init --upgrade."""

    def test_no_workflow_exits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            cmd_upgrade(_upgrade_args())

    def test_already_up_to_date(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_and_get_path(tmp_path, monkeypatch)
        cmd_upgrade(_upgrade_args())
        assert "Already up to date" in capsys.readouterr().out

    def test_preserves_user_customization(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User customizations are preserved by three-way merge."""
        wf = _init_and_get_path(tmp_path, monkeypatch)
        # Change the workflow name — user customization
        text = wf.read_text().replace(
            "name: Release Wheels",
            "name: My Custom Release",
        )
        wf.write_text(text)
        _git_commit_wf(wf)

        # Decline editor if conflicts arise
        monkeypatch.setattr("builtins.input", lambda _: "n")
        cmd_upgrade(_upgrade_args())

        result = wf.read_text()
        assert "My Custom Release" in result
