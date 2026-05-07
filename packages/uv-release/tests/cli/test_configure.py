from __future__ import annotations

from pathlib import Path

import diny
import pytest
import tomlkit

from conftest import read_toml, run_cli


class TestConfigure:
    def test_show_mode(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with diny.provide():
            run_cli("configure")
        out = capsys.readouterr().out
        # KV grammar: "key  value" (space-aligned, no colon).
        assert "latest" in out and "pkg-a" in out
        assert "python_version" in out and "3.12" in out

    def test_set_latest(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "--latest", "pkg-b")
        cfg = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["config"]
        assert cfg["latest"] == "pkg-b"

    def test_include(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "--include", "pkg-a")
        cfg = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["config"]
        assert "pkg-a" in cfg["include"]

    def test_exclude(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "--exclude", "pkg-b")
        cfg = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["config"]
        assert "pkg-b" in cfg["exclude"]

    def test_remove(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "--include", "pkg-a", "--exclude", "pkg-b")
        with diny.provide():
            run_cli("configure", "--remove", "pkg-a", "pkg-b")
        cfg = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["config"]
        assert "include" not in cfg
        assert "exclude" not in cfg

    def test_clear(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "--clear")
        cfg = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["config"]
        assert "latest" not in cfg
        assert cfg["python_version"] == "3.12"

    def test_include_and_exclude_together(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("configure", "--include", "pkg-a", "--exclude", "pkg-b")
        cfg = read_toml(workspace / "pyproject.toml")["tool"]["uvr"]["config"]
        assert "pkg-a" in cfg["include"]
        assert "pkg-b" in cfg["exclude"]

    def test_preserves_version_fields(self, workspace: Path) -> None:
        """workflow-version and skill-version must survive configure mutations."""
        pyproject = workspace / "pyproject.toml"
        doc = tomlkit.parse(pyproject.read_text())
        config = doc["tool"]["uvr"]["config"]  # type: ignore[index]
        config["workflow-version"] = "0.30.0"  # type: ignore[index]
        config["skill-version"] = "0.30.0"  # type: ignore[index]
        pyproject.write_text(tomlkit.dumps(doc))

        with diny.provide():
            run_cli("configure", "--exclude", "pkg-b")

        cfg = read_toml(pyproject)["tool"]["uvr"]["config"]
        assert cfg["workflow-version"] == "0.30.0"
        assert cfg["skill-version"] == "0.30.0"
