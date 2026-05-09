"""Tests for command execute() methods that call external tools.

Each command is tested with mocked subprocess.run to verify it
constructs the right shell command and handles exit codes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from uv_release.commands.dispatch import DispatchWorkflowCommand
from uv_release.commands.download import (
    DownloadRunArtifactsCommand,
    DownloadWheelsCommand,
)
from uv_release.commands.publish import PublishToIndexCommand


class TestDispatchWorkflowCommand:
    def test_calls_gh_workflow_run(self) -> None:
        cmd = DispatchWorkflowCommand(label="Dispatch", plan_json='{"jobs":[]}')
        calls: list[list[str]] = []

        def _mock(args, **kwargs):
            calls.append(list(args))
            if args[0] == "git":
                return subprocess.CompletedProcess(args, 0, stdout="main\n")
            return subprocess.CompletedProcess(args, 0, stdout="[]")

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        gh_call = next(c for c in calls if c[0] == "gh")
        assert "workflow" in gh_call
        assert "run" in gh_call
        assert "release.yml" in gh_call

    def test_failure_returns_nonzero(self) -> None:
        cmd = DispatchWorkflowCommand(label="Dispatch", plan_json="{}")

        def _mock(args, **kwargs):
            if args[0] == "git":
                return subprocess.CompletedProcess(args, 0, stdout="main\n")
            return subprocess.CompletedProcess(args, 1)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 1


class TestDownloadWheelsCommand:
    def test_calls_gh_release_download(self) -> None:
        cmd = DownloadWheelsCommand(
            label="Download", tag_name="pkg/v1.0.0", pattern="*.whl", output_dir="dist"
        )
        calls: list[list[str]] = []

        def _mock(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        assert any("gh" in c and "release" in c and "download" in c for c in calls)
        assert any("pkg/v1.0.0" in c for c in calls)

    def test_failure_returns_nonzero(self) -> None:
        cmd = DownloadWheelsCommand(
            label="Download", tag_name="pkg/v1.0.0", pattern="*.whl"
        )

        def _mock(args, **kwargs):
            return subprocess.CompletedProcess(args, 1)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 1


class TestDownloadRunArtifactsCommand:
    def test_calls_gh_run_download(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RUN_ID", "99999")
        out = tmp_path / "dist"
        out.mkdir()
        cmd = DownloadRunArtifactsCommand(label="Download", output_dir=str(out))
        calls: list[list[str]] = []

        def _mock(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        gh_call = next(c for c in calls if c[0] == "gh")
        assert "run" in gh_call
        assert "download" in gh_call
        assert "99999" in gh_call

    def test_no_run_id_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RUN_ID", raising=False)
        cmd = DownloadRunArtifactsCommand(label="Download")
        rc = cmd.execute()
        assert rc == 0

    def test_failure_returns_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RUN_ID", "99999")
        cmd = DownloadRunArtifactsCommand(label="Download")

        def _mock(args, **kwargs):
            return subprocess.CompletedProcess(args, 1)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 1


class TestPublishToIndexCommand:
    def test_calls_uv_publish(self, tmp_path: Path) -> None:
        # Create a fake wheel so the glob finds something.
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "my_pkg-1.0.0-py3-none-any.whl").write_text("")

        cmd = PublishToIndexCommand(
            label="Publish", package_name="my-pkg", dist_dir=str(dist), index="pypi"
        )
        calls: list[list[str]] = []

        def _mock(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        uv_call = next(c for c in calls if c[0] == "uv")
        assert "publish" in uv_call
        assert "--index" in uv_call
        assert "pypi" in uv_call
        assert any(".whl" in arg for arg in uv_call)

    def test_no_wheels_returns_error(self, tmp_path: Path) -> None:
        dist = tmp_path / "dist"
        dist.mkdir()
        cmd = PublishToIndexCommand(
            label="Publish", package_name="my-pkg", dist_dir=str(dist)
        )
        rc = cmd.execute()
        assert rc == 1

    def test_failure_returns_nonzero(self, tmp_path: Path) -> None:
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "my_pkg-1.0.0-py3-none-any.whl").write_text("")
        cmd = PublishToIndexCommand(
            label="Publish", package_name="my-pkg", dist_dir=str(dist)
        )

        def _mock(args, **kwargs):
            return subprocess.CompletedProcess(args, 1)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 1
