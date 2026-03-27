"""Tests for the init command."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from uv_release_monorepo.cli import cmd_init

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
