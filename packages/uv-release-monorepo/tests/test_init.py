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
        assert "build:" in text
        assert "release:" in text
        assert "finalize:" in text

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
    """Scaffold a workspace and init the workflow, return the release.yml path."""
    import subprocess as _sp

    _write_workspace_repo(tmp_path, ["pkg-alpha"])
    monkeypatch.chdir(tmp_path)
    _sp.run(["git", "init"], capture_output=True, check=True)
    _sp.run(["git", "add", "-A"], capture_output=True, check=True)
    _sp.run(
        ["git", "commit", "-m", "init"],
        capture_output=True,
        check=True,
        env={
            **__import__("os").environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )
    cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))
    wf = tmp_path / ".github" / "workflows" / "release.yml"
    _sp.run(["git", "add", str(wf)], capture_output=True, check=True)
    _sp.run(
        ["git", "commit", "-m", "add workflow"],
        capture_output=True,
        check=True,
        env={
            **__import__("os").environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
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
    """Tests for uvr init --upgrade."""

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
