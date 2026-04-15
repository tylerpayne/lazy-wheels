"""Integration tests for ``uvr workflow validate``."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from uv_release.cli.workflow import cmd_init_dispatch
from uv_release.cli.workflow.validate import cmd_validate


def _ns(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


class TestWorkflowValidate:
    def test_validates_clean_workflow(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Init first
        cmd_init_dispatch(
            _ns(
                workflow_dir=".github/workflows",
                force=False,
                upgrade=False,
                base_only=False,
                editor=None,
            )
        )
        capsys.readouterr()

        cmd_validate(_ns(workflow_dir=".github/workflows", diff=False))
        out = capsys.readouterr().out
        assert "OK" in out
        assert "0 errors" in out

    def test_validates_modified_workflow(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_init_dispatch(
            _ns(
                workflow_dir=".github/workflows",
                force=False,
                upgrade=False,
                base_only=False,
                editor=None,
            )
        )
        capsys.readouterr()

        # Modify the workflow
        dest = workspace / ".github/workflows/release.yml"
        dest.write_text(dest.read_text() + "\n# user change\n")

        cmd_validate(_ns(workflow_dir=".github/workflows", diff=False))
        out = capsys.readouterr().out
        assert "warning" in out

    def test_diff_flag_shows_diff(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_init_dispatch(
            _ns(
                workflow_dir=".github/workflows",
                force=False,
                upgrade=False,
                base_only=False,
                editor=None,
            )
        )
        capsys.readouterr()

        dest = workspace / ".github/workflows/release.yml"
        dest.write_text(dest.read_text() + "\n# user change\n")

        cmd_validate(_ns(workflow_dir=".github/workflows", diff=True))
        out = capsys.readouterr().out
        assert "user change" in out

    def test_missing_workflow_exits(self, workspace: Path) -> None:
        with pytest.raises(SystemExit):
            cmd_validate(_ns(workflow_dir=".github/workflows", diff=False))

    def test_missing_required_job_fails(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dest = workspace / ".github/workflows/release.yml"
        dest.parent.mkdir(parents=True)
        dest.write_text(
            "name: Release\non:\n  workflow_dispatch:\njobs:\n  custom-job:\n    runs-on: ubuntu-latest\n"
        )

        with pytest.raises(SystemExit):
            cmd_validate(_ns(workflow_dir=".github/workflows", diff=False))
        out = capsys.readouterr().out
        assert "FAIL" in out
