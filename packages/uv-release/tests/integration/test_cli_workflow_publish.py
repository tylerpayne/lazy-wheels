"""Integration tests for ``uvr workflow publish``."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import tomlkit


def _ns(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _publish_ns(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "index": None,
        "environment": None,
        "trusted_publishing": None,
        "include_packages": None,
        "exclude_packages": None,
        "remove_packages": None,
        "clear": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _read_publish(workspace: Path) -> dict:
    doc = tomlkit.loads((workspace / "pyproject.toml").read_text())
    return dict(doc.get("tool", {}).get("uvr", {}).get("publish", {}))


class TestWorkflowPublish:
    def test_show_empty(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from uv_release.cli.workflow.publish import cmd_publish_config

        cmd_publish_config(_publish_ns())
        out = capsys.readouterr().out
        assert "No publish config" in out

    def test_set_index(self, workspace: Path) -> None:
        from uv_release.cli.workflow.publish import cmd_publish_config

        cmd_publish_config(_publish_ns(index="https://pypi.org/simple"))
        config = _read_publish(workspace)
        assert config["index"] == "https://pypi.org/simple"

    def test_set_environment(self, workspace: Path) -> None:
        from uv_release.cli.workflow.publish import cmd_publish_config

        cmd_publish_config(_publish_ns(environment="production"))
        config = _read_publish(workspace)
        assert config["environment"] == "production"

    def test_set_trusted_publishing(self, workspace: Path) -> None:
        from uv_release.cli.workflow.publish import cmd_publish_config

        cmd_publish_config(_publish_ns(trusted_publishing="always"))
        config = _read_publish(workspace)
        assert config["trusted-publishing"] == "always"

    def test_include_packages(self, workspace: Path) -> None:
        from uv_release.cli.workflow.publish import cmd_publish_config

        cmd_publish_config(_publish_ns(include_packages=["alpha"]))
        config = _read_publish(workspace)
        assert "alpha" in config.get("include", [])

    def test_exclude_packages(self, workspace: Path) -> None:
        from uv_release.cli.workflow.publish import cmd_publish_config

        cmd_publish_config(_publish_ns(exclude_packages=["beta"]))
        config = _read_publish(workspace)
        assert "beta" in config.get("exclude", [])

    def test_clear(self, workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from uv_release.cli.workflow.publish import cmd_publish_config

        cmd_publish_config(_publish_ns(index="test"))
        cmd_publish_config(_publish_ns(clear=True))
        out = capsys.readouterr().out
        assert "Cleared" in out
