"""Commands for building and downloading wheels."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..types import Command, Package

_UVR_RUNNER_ENV = "UVR_RUNNER"


class BuildCommand(Command):
    """Build a package via uv build."""

    type: Literal["build"] = "build"
    package: Package
    runners: list[list[str]] = Field(default_factory=list)
    out_dir: str = "dist/"
    find_links: list[str] = Field(default_factory=lambda: ["dist/", "deps/"])

    def execute(self) -> int:
        import json
        import os
        import subprocess

        # If UVR_RUNNER is set, skip if this command's runners don't match
        runner_json = os.environ.get(_UVR_RUNNER_ENV, "")
        if runner_json and self.runners:
            current_runner = json.loads(runner_json)
            if current_runner not in self.runners:
                return 0

        args = ["uv", "build", self.package.path, "--out-dir", self.out_dir]
        for link_dir in self.find_links:
            args.extend(["--find-links", link_dir])
        args.append("--no-sources")
        return subprocess.run(args).returncode


class DownloadWheelsCommand(Command):
    """Download wheels from GitHub releases for unchanged deps."""

    type: Literal["download_wheels"] = "download_wheels"
    packages: list[Package]
    release_tags: dict[str, str]  # {package_name: release_tag_name} — from plan context
    directory: str = "deps"

    def execute(self) -> int:
        import subprocess

        for pkg in self.packages:
            tag = self.release_tags.get(pkg.name)
            if not tag:
                continue
            result = subprocess.run(
                [
                    "gh",
                    "release",
                    "download",
                    tag,
                    "--dir",
                    self.directory,
                    "--clobber",
                ],
            )
            if result.returncode != 0:
                return result.returncode
        return 0
