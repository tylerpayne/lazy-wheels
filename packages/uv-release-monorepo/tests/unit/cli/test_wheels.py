"""Tests for the wheels command."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from uv_release_monorepo.cli.wheels import cmd_wheels


class TestCmdWheels:
    """Tests for cmd_wheels()."""

    def _fake_run_release(self, tag: str, dist_name: str, wheel_name: str) -> tuple:
        """Return a fake subprocess.run for release-based downloads."""
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            cmd = list(cmd)
            calls.append(cmd)
            result = MagicMock()
            result.returncode = 0

            if "view" in cmd:
                result.stdout = json.dumps({"assets": [{"name": wheel_name}]})
            elif "download" in cmd:
                dir_idx = cmd.index("--dir") + 1
                whl_dir = Path(cmd[dir_idx])
                whl_dir.mkdir(parents=True, exist_ok=True)
                (whl_dir / wheel_name).write_bytes(b"")
            elif "list" in cmd:
                result.stdout = json.dumps([{"tagName": tag}])
            else:
                result.stdout = ""
            return result

        return fake_run, calls

    def test_wheels_from_release_tag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Downloads wheels using --release-tag."""
        out = str(tmp_path / "out")
        fake_run, calls = self._fake_run_release(
            "my-pkg/v1.0.0", "my_pkg", "my_pkg-1.0.0-py3-none-any.whl"
        )
        monkeypatch.setattr(subprocess, "run", fake_run)

        args = argparse.Namespace(
            package="acme/repo/my-pkg",
            release_tag="my-pkg/v1.0.0",
            run_id=None,
            output=out,
        )
        cmd_wheels(args)

        # Should have called gh release view + download
        view_calls = [c for c in calls if "view" in c]
        assert len(view_calls) == 1
        assert "my-pkg/v1.0.0" in view_calls[0]

        # Wheel should be in output dir
        wheels = list(Path(out).glob("*.whl"))
        assert len(wheels) == 1

    def test_wheels_from_run_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Downloads wheels using --run-id."""
        out = str(tmp_path / "out")

        def fake_run(cmd, **kwargs):
            cmd = list(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""

            if "download" in cmd:
                # gh run download extracts into subdirs
                dir_idx = cmd.index("--dir") + 1
                base = Path(cmd[dir_idx])
                artifact_dir = base / "wheels-ubuntu-latest"
                artifact_dir.mkdir(parents=True, exist_ok=True)
                (artifact_dir / "my_pkg-1.0.0-py3-none-any.whl").write_bytes(b"")
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        args = argparse.Namespace(
            package="acme/repo/my-pkg",
            release_tag=None,
            run_id="12345",
            output=out,
        )
        cmd_wheels(args)

        wheels = list(Path(out).glob("*.whl"))
        assert len(wheels) == 1
        assert wheels[0].name == "my_pkg-1.0.0-py3-none-any.whl"

    def test_wheels_defaults_to_latest_release(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without --release-tag or --run-id, resolves latest release."""
        out = str(tmp_path / "out")
        fake_run, calls = self._fake_run_release(
            "my-pkg/v2.0.0", "my_pkg", "my_pkg-2.0.0-py3-none-any.whl"
        )
        monkeypatch.setattr(subprocess, "run", fake_run)

        args = argparse.Namespace(
            package="acme/repo/my-pkg",
            release_tag=None,
            run_id=None,
            output=out,
        )
        cmd_wheels(args)

        # Should have called gh release list to find latest tag
        list_calls = [c for c in calls if "list" in c]
        assert len(list_calls) == 1

        wheels = list(Path(out).glob("*.whl"))
        assert len(wheels) == 1
