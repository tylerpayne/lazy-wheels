"""Tests for the init and upgrade commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from uv_release_monorepo.cli import cmd_init, cmd_upgrade
from uv_release_monorepo.cli._yaml import _load_yaml

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
    _write_workspace_repo(tmp_path, ["pkg-alpha"])
    monkeypatch.chdir(tmp_path)
    cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))
    return tmp_path / ".github" / "workflows" / "release.yml"


def _upgrade_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = dict(
        workflow_dir=".github/workflows",
        yes=True,
        upgrade=True,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


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

    def test_updates_matched_steps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Steps matched by name are updated; unmatched user steps survive."""
        wf = _init_and_get_path(tmp_path, monkeypatch)
        doc = _load_yaml(wf)
        # Tamper a named step
        for step in doc["jobs"]["finalize"]["steps"]:
            if step.get("name") == "Finalize release":
                step["run"] = "echo tampered"
        # Add a custom user step
        doc["jobs"]["finalize"]["steps"].append(
            {"name": "My custom step", "run": "echo hello"}
        )
        from uv_release_monorepo.cli._yaml import _write_yaml

        _write_yaml(wf, doc)

        cmd_upgrade(_upgrade_args())

        upgraded = _load_yaml(wf)
        steps = upgraded["jobs"]["finalize"]["steps"]
        # Matched step was restored
        finalize_step = next(s for s in steps if s.get("name") == "Finalize release")
        assert finalize_step["run"] != "echo tampered"
        # Custom step preserved
        assert any(s.get("name") == "My custom step" for s in steps)

    def test_preserves_extra_jobs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wf = _init_and_get_path(tmp_path, monkeypatch)
        doc = _load_yaml(wf)
        doc["jobs"]["my-custom-job"] = {"runs-on": "ubuntu-latest", "steps": []}
        # Tamper a frozen field to ensure the upgrade has something to do
        doc["jobs"]["finalize"]["steps"] = [{"run": "echo tampered"}]
        from uv_release_monorepo.cli._yaml import _write_yaml

        _write_yaml(wf, doc)

        cmd_upgrade(_upgrade_args())

        upgraded = _load_yaml(wf)
        assert "my-custom-job" in upgraded["jobs"]

    def test_preserves_extra_triggers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wf = _init_and_get_path(tmp_path, monkeypatch)
        doc = _load_yaml(wf)
        doc["on"]["push"] = {"branches": ["main"]}
        doc["jobs"]["finalize"]["steps"] = [{"run": "echo tampered"}]
        from uv_release_monorepo.cli._yaml import _write_yaml

        _write_yaml(wf, doc)

        cmd_upgrade(_upgrade_args())

        upgraded = _load_yaml(wf)
        assert "push" in upgraded["on"]

    def test_preserves_custom_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wf = _init_and_get_path(tmp_path, monkeypatch)
        doc = _load_yaml(wf)
        doc["jobs"]["build"]["env"] = {"MY_VAR": "hello"}
        doc["jobs"]["finalize"]["steps"] = [{"run": "echo tampered"}]
        from uv_release_monorepo.cli._yaml import _write_yaml

        _write_yaml(wf, doc)

        cmd_upgrade(_upgrade_args())

        upgraded = _load_yaml(wf)
        assert upgraded["jobs"]["build"]["env"]["MY_VAR"] == "hello"

    @patch("uv_release_monorepo.cli.init.subprocess.run")
    def test_declined_no_changes(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        wf = _init_and_get_path(tmp_path, monkeypatch)
        doc = _load_yaml(wf)
        doc["jobs"]["finalize"]["steps"].append({"id": "extra", "run": "echo extra"})
        from uv_release_monorepo.cli._yaml import _write_yaml

        _write_yaml(wf, doc)
        original = wf.read_text()

        # Simulate git add -p returning 1 (user quit), git show returning nothing
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        cmd_upgrade(_upgrade_args(yes=False))

        assert wf.read_text() == original
