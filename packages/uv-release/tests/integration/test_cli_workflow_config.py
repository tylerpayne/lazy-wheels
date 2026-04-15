"""Integration tests for ``uvr workflow config``."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import tomlkit


def _ns(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _read_config(workspace: Path) -> dict:
    doc = tomlkit.loads((workspace / "pyproject.toml").read_text())
    return dict(doc.get("tool", {}).get("uvr", {}).get("config", {}))


class TestWorkflowConfig:
    def test_show_empty_config(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from uv_release.cli.workflow.config import cmd_config

        cmd_config(
            _ns(
                editor=None,
                latest=None,
                include_packages=None,
                exclude_packages=None,
                remove_packages=None,
                clear=False,
            )
        )
        out = capsys.readouterr().out
        assert "No workspace config" in out

    def test_set_latest(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from uv_release.cli.workflow.config import cmd_config

        cmd_config(
            _ns(
                editor=None,
                latest="alpha",
                include_packages=None,
                exclude_packages=None,
                remove_packages=None,
                clear=False,
            )
        )
        config = _read_config(workspace)
        assert config.get("latest") == "alpha"

    def test_set_include(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from uv_release.cli.workflow.config import cmd_config

        cmd_config(
            _ns(
                editor=None,
                latest=None,
                include_packages=["alpha", "beta"],
                exclude_packages=None,
                remove_packages=None,
                clear=False,
            )
        )
        config = _read_config(workspace)
        assert "alpha" in config.get("include", [])
        assert "beta" in config.get("include", [])

    def test_set_exclude(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from uv_release.cli.workflow.config import cmd_config

        cmd_config(
            _ns(
                editor=None,
                latest=None,
                include_packages=None,
                exclude_packages=["gamma"],
                remove_packages=None,
                clear=False,
            )
        )
        config = _read_config(workspace)
        assert "gamma" in config.get("exclude", [])

    def test_clear(self, workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from uv_release.cli.workflow.config import cmd_config

        # Set something first
        cmd_config(
            _ns(
                editor=None,
                latest="alpha",
                include_packages=None,
                exclude_packages=None,
                remove_packages=None,
                clear=False,
            )
        )
        # Clear it
        cmd_config(
            _ns(
                editor=None,
                latest=None,
                include_packages=None,
                exclude_packages=None,
                remove_packages=None,
                clear=True,
            )
        )
        out = capsys.readouterr().out
        assert "Cleared" in out
