from __future__ import annotations

from pathlib import Path

import diny
import pytest
import yaml

from conftest import run_cli


class TestWorkflowValidate:
    def test_missing_file(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (workspace / ".github" / "workflows" / "release.yml").unlink()
        with diny.provide():
            run_cli("workflow", "validate")
        # ui.error writes to stderr.
        assert "does not exist" in capsys.readouterr().err

    def test_has_all_required_jobs(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with diny.provide():
            run_cli("workflow", "validate")
        out = capsys.readouterr().out
        assert "missing" not in out.lower()

    def test_missing_required_jobs(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wf = workspace / ".github" / "workflows" / "release.yml"
        wf.write_text(yaml.dump({"jobs": {"build": {}}}))
        with diny.provide():
            run_cli("workflow", "validate")
        out = capsys.readouterr().out
        assert "validate" in out and "missing" in out.lower()

    def test_custom_workflow_dir(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        custom = workspace / "ci"
        custom.mkdir()
        (custom / "release.yml").write_text(
            yaml.dump(
                {
                    "jobs": {
                        "validate": {},
                        "build": {},
                        "release": {},
                        "publish": {},
                        "bump": {},
                    }
                }
            )
        )
        with diny.provide():
            run_cli("workflow", "validate", "--workflow-dir", "ci")
        out = capsys.readouterr().out
        assert "missing" not in out.lower()


class TestWorkflowUpgrade:
    def test_scaffolds_workflow(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (workspace / ".github" / "workflows" / "release.yml").unlink()
        with diny.provide():
            run_cli("workflow", "install")
        out = capsys.readouterr().out
        assert "Write" in out or "workflow-upgrade" in out
        wf = workspace / ".github" / "workflows" / "release.yml"
        assert wf.exists()
