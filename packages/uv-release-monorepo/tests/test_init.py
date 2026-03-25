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
        """init writes the executor workflow template."""
        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(workflow_dir=".github/workflows")
        cmd_init(args)

        workflow = tmp_path / ".github" / "workflows" / "release.yml"
        assert workflow.exists()
        assert "jobs:\n  build:" in workflow.read_text()

    def test_init_workflow_has_uvr_version_input(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Generated workflow has uvr_version input (no baked-in version)."""
        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(workflow_dir=".github/workflows")
        cmd_init(args)

        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "uvr_version" in workflow
        assert "uv-release-monorepo=={0}" in workflow
        assert "__UVR_VERSION__" not in workflow
