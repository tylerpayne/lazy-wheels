"""Tests for CommandArgs base and CLI argument parsing."""

from __future__ import annotations

import argparse

from uv_release.cli._args import CommandArgs


class TestCommandArgs:
    def test_from_namespace_basic(self) -> None:
        class MyArgs(CommandArgs):
            name: str = ""
            count: int = 0

        ns = argparse.Namespace(name="test", count=5)
        parsed = MyArgs.from_namespace(ns)
        assert parsed.name == "test"
        assert parsed.count == 5

    def test_from_namespace_frozen(self) -> None:
        class MyArgs(CommandArgs):
            name: str = ""

        ns = argparse.Namespace(name="test")
        parsed = MyArgs.from_namespace(ns)
        import pytest

        with pytest.raises(Exception):
            parsed.name = "changed"

    def test_from_namespace_ignores_extra_fields(self) -> None:
        class MyArgs(CommandArgs):
            name: str = ""

        ns = argparse.Namespace(name="test", func=lambda: None, command="status")
        parsed = MyArgs.from_namespace(ns)
        assert parsed.name == "test"
