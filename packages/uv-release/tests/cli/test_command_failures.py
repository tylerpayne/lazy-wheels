"""Tests for command failure handling.

Each test mocks a single external command to return non-zero and verifies
the pipeline aborts (check=True) or continues (check=False).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import diny
import pytest

from conftest import run_cli


def _mock_one_command(
    monkeypatch: pytest.MonkeyPatch,
    fail_cmd: str,
    fail_subcmd: str = "",
    exit_code: int = 1,
) -> None:
    """Mock a single command to fail. All others succeed."""
    _real = subprocess.run

    def _patched(args: str | list[str], **kwargs):
        if not isinstance(args, list):
            return _real(args, **kwargs)
        if args[0] == fail_cmd:
            if not fail_subcmd or (len(args) >= 2 and args[1] == fail_subcmd):
                # Don't fail read-only pre-checks (git tag -l, git status).
                if not (args[0] == "git" and len(args) >= 3 and args[2] == "-l"):
                    if not (args[0] == "git" and args[1] == "status"):
                        return subprocess.CompletedProcess(
                            args, exit_code, stdout="", stderr=""
                        )
        # Succeed for all other external commands.
        if args[0] == "gh":
            if len(args) >= 3 and args[1] == "release" and args[2] == "view":
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if args[0] == "uv":
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if (
            args[0] == "git"
            and len(args) >= 2
            and args[1] in ("tag", "push", "pull", "config")
        ):
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        # Let git status run for real so CommitCommand can detect changes.
        return _real(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _patched)


class TestBuildFailures:
    def test_uv_build_failure_aborts(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """uv build has check=True. Non-zero should abort."""
        _mock_one_command(monkeypatch, "uv", "build")
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("build", "--all-packages")

    def test_uv_build_success_completes(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _real = subprocess.run

        def _patched(args: str | list[str], **kwargs):
            if isinstance(args, list) and args[0] == "uv":
                return subprocess.CompletedProcess(args, 0)
            return _real(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", _patched)
        with diny.provide():
            run_cli("build", "--all-packages")
        assert "Done" in capsys.readouterr().out


class TestBumpFailures:
    def test_lock_failure_aborts(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SyncLockfileCommand has check=True. Failure should abort.

        We need uv.lock regeneration to succeed before committing, otherwise
        the bump commit ships pyproject.toml updates without the matching
        lockfile and downstream installs are inconsistent.
        """
        _mock_one_command(monkeypatch, "uv", "lock")
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("version", "--bump", "minor", "--no-commit", "--no-push")

    def test_git_commit_failure_aborts(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CommitCommand has check=True. Failure should abort."""
        _mock_one_command(monkeypatch, "git", "commit")
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("version", "--bump", "minor", "--no-push")

    def test_git_push_failure_aborts(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PushCommand has check=True. Failure should abort."""
        _mock_one_command(monkeypatch, "git", "push")
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("version", "--bump", "minor")


class TestLocalReleaseFailures:
    """Test failure of each command in a local release pipeline."""

    def _mock_all_succeed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _real = subprocess.run

        def _patched(args: str | list[str], **kwargs):
            if isinstance(args, list) and args[0] == "gh":
                # gh release view should return 1 (not found) so create proceeds.
                if len(args) >= 3 and args[1] == "release" and args[2] == "view":
                    return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            if isinstance(args, list) and args[0] == "uv":
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            if (
                isinstance(args, list)
                and args[0] == "git"
                and len(args) >= 2
                and args[1] in ("tag", "push", "pull", "config", "status")
            ):
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            return _real(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", _patched)

    def test_all_succeed(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._mock_all_succeed(monkeypatch)
        monkeypatch.setenv("RUN_ID", "12345")
        with diny.provide():
            run_cli("release", "--where", "local", "--dev", "-y")

    def test_git_tag_failure_aborts(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_one_command(monkeypatch, "git", "tag")
        monkeypatch.setenv("RUN_ID", "12345")
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("release", "--where", "local", "--dev", "-y")

    def test_git_push_tags_failure_aborts(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_one_command(monkeypatch, "git", "push")
        monkeypatch.setenv("RUN_ID", "12345")
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("release", "--where", "local", "--dev", "-y")

    def test_gh_release_create_failure_aborts(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _mock_one_command(monkeypatch, "gh", "release")
        monkeypatch.setenv("RUN_ID", "12345")
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("release", "--where", "local", "--dev", "-y")
