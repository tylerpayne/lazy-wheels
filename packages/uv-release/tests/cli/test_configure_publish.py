from __future__ import annotations

from pathlib import Path

import diny
import pytest

from conftest import read_toml, run_cli


class TestConfigurePublish:
    def test_show_mode(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with diny.provide():
            run_cli("configure", "publish")
        out = capsys.readouterr().out
        # KV grammar: "key  value" (space-aligned, no colon).
        assert "index" in out and "(not set)" in out

    def test_set_index(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "publish", "--index", "pypi")
        pub = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["publish"]
        assert pub["index"] == "pypi"

    def test_set_environment(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "publish", "--environment", "release")
        pub = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["publish"]
        assert pub["environment"] == "release"

    def test_set_trusted_publishing(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "publish", "--trusted-publishing", "always")
        pub = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["publish"]
        assert pub["trusted-publishing"] == "always"

    def test_include_exclude(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "publish", "--include", "pkg-a", "--exclude", "pkg-b")
        pub = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["publish"]
        assert "pkg-a" in pub["include"]
        assert "pkg-b" in pub["exclude"]

    def test_clear(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "publish", "--index", "pypi")
        with diny.provide():
            run_cli("configure", "publish", "--clear")
        pub = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["publish"]
        assert "index" not in pub
