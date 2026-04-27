"""Commands for creating GitHub releases and publishing to indexes."""

from __future__ import annotations

from typing import Literal

from ..types import Command, Publishing, Release, Tag


class CreateReleaseCommand(Command):
    """Create a GitHub release with wheels via gh CLI."""

    type: Literal["create_release"] = "create_release"
    release: Release

    def execute(self) -> int:
        import subprocess

        tag = Tag.release_tag_name(
            self.release.package.name, self.release.release_version
        )
        files = _find_dist_wheels(
            self.release.package.dist_name, self.release.release_version.raw
        )
        args = [
            "gh",
            "release",
            "create",
            tag,
            "--title",
            f"{self.release.package.name} {self.release.release_version.raw}",
            "--notes",
            self.release.release_notes,
        ]
        if self.release.make_latest:
            args.append("--latest")
        else:
            args.append("--latest=false")
        args.extend(files)
        return subprocess.run(args).returncode


class PublishToIndexCommand(Command):
    """Upload wheels to a package index via uv publish."""

    type: Literal["publish_to_index"] = "publish_to_index"
    release: Release
    publishing: Publishing

    def execute(self) -> int:
        import subprocess

        files = _find_dist_wheels(
            self.release.package.dist_name, self.release.release_version.raw
        )
        args = ["uv", "publish"]
        if self.publishing.index:
            args.extend(["--index", self.publishing.index])
        if self.publishing.trusted_publishing:
            args.extend(["--trusted-publishing", self.publishing.trusted_publishing])
        args.extend(files)
        return subprocess.run(args).returncode


def _find_dist_wheels(dist_name: str, version_raw: str) -> list[str]:
    """Find wheel files matching a dist name and version in dist/."""
    from glob import glob as glob_fn

    pattern = f"dist/{dist_name}-{version_raw}-*.whl"
    return sorted(glob_fn(pattern))
