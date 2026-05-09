"""Tests for interactive commands: CommandGroup confirmation and MergeUpgradeCommand editor."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from uv_release.commands.group import CommandGroup
from uv_release.commands.merge import MergeUpgradeCommand
from uv_release.commands.shell import ShellCommand


class TestCommandGroup:
    def _group(self) -> CommandGroup:
        return CommandGroup(
            label="Run dangerous stuff",
            needs_confirmation=True,
            commands=[
                ShellCommand(label="echo hello", args=["echo", "hello"]),
            ],
        )

    def test_confirmed_executes(self) -> None:
        group = self._group()
        with patch("builtins.input", return_value="y"):
            rc = group.execute()
        assert rc == 0

    def test_declined_skips(self) -> None:
        group = self._group()
        with patch("builtins.input", return_value="n"):
            rc = group.execute()
        assert rc == 0

    def test_eof_skips(self) -> None:
        group = self._group()
        with patch("builtins.input", side_effect=EOFError):
            rc = group.execute()
        assert rc == 0

    def test_no_confirmation_always_runs(self) -> None:
        group = CommandGroup(
            label="safe",
            needs_confirmation=False,
            commands=[ShellCommand(label="echo", args=["echo", "ok"])],
        )
        rc = group.execute()
        assert rc == 0

    def test_inner_command_failure_propagates(self) -> None:
        group = CommandGroup(
            label="will fail",
            needs_confirmation=False,
            commands=[ShellCommand(label="fail", args=["false"])],
        )
        rc = group.execute()
        assert rc != 0


class TestMergeUpgradeCommand:
    def _setup(
        self, tmp_path: Path, base_text: str, current_text: str
    ) -> tuple[Path, Path]:
        """Pre-populate the base cache and the current file on disk."""
        base_path = tmp_path / "base.txt"
        base_path.write_text(base_text)
        target = tmp_path / "out.txt"
        target.write_text(current_text)
        return target, base_path

    def test_no_change_reports_up_to_date(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target, base_path = self._setup(tmp_path, "same", "same")
        cmd = MergeUpgradeCommand(
            label="Merge",
            file_path=str(target),
            base_path=str(base_path),
            incoming_content="same",
        )
        rc = cmd.execute()
        assert rc == 0
        assert "up to date" in capsys.readouterr().out

    def test_clean_merge(self, tmp_path: Path) -> None:
        target, base_path = self._setup(tmp_path, "line1\nline2\n", "line1\nline2\n")
        cmd = MergeUpgradeCommand(
            label="Merge",
            file_path=str(target),
            base_path=str(base_path),
            incoming_content="line1\nline2\nline3\n",
        )
        rc = cmd.execute()
        assert rc == 0
        assert "line3" in target.read_text()
        # Base file is a transient cache, owned by FetchWorkflowBaseCommand.
        # MergeUpgradeCommand must not overwrite it.
        assert base_path.read_text() == "line1\nline2\n"

    def test_conflict_without_editor(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target, base_path = self._setup(tmp_path, "line1\noriginal\n", "line1\nmine\n")
        cmd = MergeUpgradeCommand(
            label="Merge",
            file_path=str(target),
            base_path=str(base_path),
            incoming_content="line1\ntheirs\n",
        )
        rc = cmd.execute()
        assert rc == 0
        assert "conflicts" in capsys.readouterr().out

    def test_conflict_with_editor_resolved(self, tmp_path: Path) -> None:
        target, base_path = self._setup(tmp_path, "line1\noriginal\n", "line1\nmine\n")
        cmd = MergeUpgradeCommand(
            label="Merge",
            file_path=str(target),
            base_path=str(base_path),
            incoming_content="line1\ntheirs\n",
            editor="fake-editor",
        )
        _real = subprocess.run

        def _mock_editor_only(args, **kwargs):
            if isinstance(args, list) and args[0] == "fake-editor":
                Path(args[1]).write_text("line1\nresolved\n")
                return subprocess.CompletedProcess(args, 0)
            return _real(args, **kwargs)

        with (
            patch("builtins.input", return_value="y"),
            patch("subprocess.run", side_effect=_mock_editor_only),
        ):
            rc = cmd.execute()
        assert rc == 0
        assert "resolved" in target.read_text()

    def test_conflict_with_editor_unresolved_reverts(self, tmp_path: Path) -> None:
        original = "line1\nmine\n"
        target, base_path = self._setup(tmp_path, "line1\noriginal\n", original)
        cmd = MergeUpgradeCommand(
            label="Merge",
            file_path=str(target),
            base_path=str(base_path),
            incoming_content="line1\ntheirs\n",
            editor="fake-editor",
        )
        _real = subprocess.run

        def _mock_editor_only(args, **kwargs):
            if isinstance(args, list) and args[0] == "fake-editor":
                return subprocess.CompletedProcess(args, 0)
            return _real(args, **kwargs)

        with (
            patch("builtins.input", return_value="y"),
            patch("subprocess.run", side_effect=_mock_editor_only),
        ):
            rc = cmd.execute()
        assert rc == 1
        assert target.read_text() == original

    def test_conflict_with_editor_declined(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target, base_path = self._setup(tmp_path, "line1\noriginal\n", "line1\nmine\n")
        cmd = MergeUpgradeCommand(
            label="Merge",
            file_path=str(target),
            base_path=str(base_path),
            incoming_content="line1\ntheirs\n",
            editor="fake-editor",
        )
        with patch("builtins.input", return_value="n"):
            rc = cmd.execute()
        assert rc == 0
