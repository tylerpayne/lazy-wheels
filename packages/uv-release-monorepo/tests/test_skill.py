"""Tests for the skill init command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from uv_release_monorepo.cli import cli, cmd_skill_init
from uv_release_monorepo.cli.skill import (
    _SKILL_FILES,
    _latest_skill_version,
    _load_skill_file,
)


class TestSkillInit:
    """Tests for the skill init command."""

    @staticmethod
    def _git_dir(tmp_path: Path) -> Path:
        """Create a minimal git repo directory."""
        (tmp_path / ".git").mkdir()
        return tmp_path

    def test_copies_all_skill_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._git_dir(tmp_path)
        monkeypatch.chdir(tmp_path)

        cmd_skill_init(argparse.Namespace(force=False))

        for name, files in _SKILL_FILES.items():
            for rel in files:
                dest = tmp_path / ".claude" / "skills" / name / rel
                assert dest.exists(), f"Missing: .claude/skills/{name}/{rel}"
                assert dest.read_text(encoding="utf-8").strip()

    def test_skips_existing_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._git_dir(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Pre-create a file with custom content
        existing = tmp_path / ".claude" / "skills" / "release" / "SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("custom content", encoding="utf-8")

        cmd_skill_init(argparse.Namespace(force=False))

        assert existing.read_text(encoding="utf-8") == "custom content"

    def test_force_overwrites_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._git_dir(tmp_path)
        monkeypatch.chdir(tmp_path)

        existing = tmp_path / ".claude" / "skills" / "release" / "SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("custom content", encoding="utf-8")

        cmd_skill_init(argparse.Namespace(force=True))

        assert existing.read_text(encoding="utf-8") != "custom content"
        assert "release" in existing.read_text(encoding="utf-8").lower()

    def test_not_git_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit):
            cmd_skill_init(argparse.Namespace(force=False))

    def test_manifest_matches_package(self) -> None:
        """Every file listed in _SKILL_FILES exists in the bundled package."""
        version = _latest_skill_version()
        for name, file_list in _SKILL_FILES.items():
            for rel in file_list:
                content = _load_skill_file(version, name, rel)
                assert content.strip(), f"Manifest lists {name}/{rel} but file is empty"


def test_cli_skill_init_parsing() -> None:
    """``uvr skill init --force`` parses correctly."""
    with patch.object(sys, "argv", ["uvr", "skill", "init", "--force"]):
        with patch("uv_release_monorepo.cli.cmd_skill_init") as mock:
            cli()
            args = mock.call_args[0][0]
            assert args.force is True
