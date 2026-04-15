"""Integration tests for ``uvr workflow runners``."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import tomlkit


def _ns(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _read_runners(workspace: Path) -> dict:
    doc = tomlkit.loads((workspace / "pyproject.toml").read_text())
    return dict(doc.get("tool", {}).get("uvr", {}).get("runners", {}))


class TestWorkflowRunners:
    def test_show_default_runners(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from uv_release.cli.workflow.runners import cmd_runners

        cmd_runners(
            _ns(package=None, add_runners=None, remove_runners=None, clear=False)
        )
        out = capsys.readouterr().out
        assert "ubuntu-latest" in out

    def test_show_single_package(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from uv_release.cli.workflow.runners import cmd_runners

        cmd_runners(
            _ns(package="alpha", add_runners=None, remove_runners=None, clear=False)
        )
        out = capsys.readouterr().out
        assert "ubuntu-latest" in out

    def test_add_runner(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from uv_release.cli.workflow.runners import cmd_runners

        cmd_runners(
            _ns(
                package="alpha",
                add_runners=["macos-latest"],
                remove_runners=None,
                clear=False,
            )
        )
        runners = _read_runners(workspace)
        assert ["macos-latest"] in runners["alpha"]

    def test_clear_runner(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from uv_release.cli.workflow.runners import cmd_runners

        # Add first
        cmd_runners(
            _ns(
                package="alpha",
                add_runners=["macos-latest"],
                remove_runners=None,
                clear=False,
            )
        )
        # Clear
        cmd_runners(
            _ns(package="alpha", add_runners=None, remove_runners=None, clear=True)
        )
        runners = _read_runners(workspace)
        assert "alpha" not in runners
