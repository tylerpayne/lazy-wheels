from __future__ import annotations

from pathlib import Path

import diny
import pytest

from conftest import run_cli


class TestInstall:
    def test_no_args_errors(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("install")
        assert "Specify packages" in capsys.readouterr().err

    def test_packages_no_remote_errors(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("install", "pkg-a")
        # ui.error renders as "error: <summary>" on stderr.
        assert "error:" in capsys.readouterr().err

    def test_dist_nonexistent_errors(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--dist with a directory that has no wheels should fail at execution."""
        dist = workspace / "empty_dist"
        dist.mkdir()
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("install", "--dist", str(dist))
        assert capsys.readouterr().err != ""
