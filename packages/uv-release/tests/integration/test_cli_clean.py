"""Integration tests for ``uvr clean``."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from uv_release.cli.clean import cmd_clean


def _ns(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


class TestCmdClean:
    def test_removes_cache_dir(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cache = workspace / ".uvr" / "cache"
        cache.mkdir(parents=True)
        (cache / "something").write_text("cached")

        cmd_clean(_ns())
        out = capsys.readouterr().out
        assert "removed" in out
        assert not cache.exists()

    def test_nothing_to_clean(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_clean(_ns())
        out = capsys.readouterr().out
        assert "Nothing to clean" in out
