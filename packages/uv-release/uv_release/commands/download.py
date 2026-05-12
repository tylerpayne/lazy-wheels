"""Download wheels from a GitHub release or CI run artifacts."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Literal

from packaging.tags import sys_tags
from packaging.utils import InvalidWheelFilename, parse_wheel_filename

from ..ui.console import console
from .base import Command


class DownloadWheelsCommand(Command):
    """Download wheels from a GitHub release, filtering to the current platform."""

    type: Literal["download_wheels"] = "download_wheels"
    tag_name: str
    pattern: str
    output_dir: str = "dist"
    all_platforms: bool = False
    # owner/name. Empty falls back to gh's default (set via `gh repo set-default`).
    repo: str = ""

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        args = [
            "gh",
            "release",
            "download",
            self.tag_name,
            "--pattern",
            self.pattern,
            "--dir",
            self.output_dir,
            "--clobber",
        ]
        if self.repo:
            args += ["--repo", self.repo]
        result = subprocess.run(args)
        if result.returncode != 0:
            return result.returncode
        if not self.all_platforms:
            self._filter_platform_wheels()
        return 0

    def _filter_platform_wheels(self) -> None:
        """Remove downloaded wheels that don't match the current platform.

        Uses packaging.tags.sys_tags(), the canonical compatibility check
        (same as pip/uv). A wheel is kept if any of its embedded tags appear
        in the current interpreter's supported tag set.
        """
        compatible = set(sys_tags())
        out = Path(self.output_dir)
        for whl in out.glob("*.whl"):
            try:
                _name, _version, _build, wheel_tags = parse_wheel_filename(whl.name)
            except InvalidWheelFilename:
                continue
            if not (wheel_tags & compatible):
                console.print(f"    Removing incompatible wheel: {whl.name}")
                whl.unlink()


class DownloadRunArtifactsCommand(Command):
    """Download build artifacts from a GitHub Actions run.

    Reads RUN_ID from the environment at execution time because the
    current run ID is not known at plan time (before CI dispatch).
    """

    type: Literal["download_run_artifacts"] = "download_run_artifacts"
    output_dir: str = "dist"
    # owner/name. Empty falls back to gh's default (set via `gh repo set-default`).
    repo: str = ""

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        run_id = os.environ.get("RUN_ID", "")
        if not run_id:
            console.print("    RUN_ID not set, skipping artifact download")
            return 0
        args = [
            "gh",
            "run",
            "download",
            run_id,
            "--dir",
            self.output_dir,
            "--pattern",
            "wheels-*",
        ]
        if self.repo:
            args += ["--repo", self.repo]
        result = subprocess.run(args)
        if result.returncode != 0:
            return result.returncode
        # gh run download creates subdirs per artifact name. Flatten into output_dir.
        out = Path(self.output_dir)
        for subdir in out.iterdir():
            if subdir.is_dir():
                for f in subdir.iterdir():
                    f.rename(out / f.name)
                subdir.rmdir()
        return 0
