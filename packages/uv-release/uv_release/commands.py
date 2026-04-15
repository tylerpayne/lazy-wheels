"""All command types. Each command is frozen and knows how to execute itself."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Discriminator, Field

from .types import Command, CommandGroup, Package, Publishing, Release, Tag, Version


class ShellCommand(Command):
    """Run a subprocess."""

    type: Literal["shell"] = "shell"
    args: list[str]

    def execute(self) -> int:
        import subprocess

        result = subprocess.run(self.args)
        return result.returncode


class CreateTagCommand(Command):
    """Create a git tag in-process."""

    type: Literal["create_tag"] = "create_tag"
    tag_name: str

    def execute(self) -> int:
        from .git import GitRepo

        repo = GitRepo()
        repo.create_tag(self.tag_name)
        return 0


class SetVersionCommand(Command):
    """Write a version to a package's pyproject.toml."""

    type: Literal["set_version"] = "set_version"
    package: Package
    version: Version

    def execute(self) -> int:
        from pathlib import Path

        import tomlkit

        pyproject_path = Path(self.package.path) / "pyproject.toml"
        doc = tomlkit.loads(pyproject_path.read_text())
        doc["project"]["version"] = self.version.raw  # type: ignore[index]
        pyproject_path.write_text(tomlkit.dumps(doc))
        return 0


class PinDepsCommand(Command):
    """Pin internal dependency versions in a package's pyproject.toml."""

    type: Literal["pin_deps"] = "pin_deps"
    package: Package
    pins: dict[str, Version]

    def execute(self) -> int:
        from pathlib import Path

        import tomlkit
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name

        pyproject_path = Path(self.package.path) / "pyproject.toml"
        doc = tomlkit.loads(pyproject_path.read_text())

        for section in ("project", "build-system"):
            key = "dependencies" if section == "project" else "requires"
            deps = doc.get(section, {}).get(key, [])
            for i, dep in enumerate(deps):
                req = Requirement(str(dep))
                name = canonicalize_name(req.name)
                if name in self.pins:
                    pinned = self.pins[name]
                    upper = pinned.bump_minor()
                    deps[i] = f"{req.name}>={pinned.raw},<{upper.raw}"

        pyproject_path.write_text(tomlkit.dumps(doc))
        return 0


class CreateReleaseCommand(Command):
    """Create a GitHub release with wheels via gh CLI."""

    type: Literal["create_release"] = "create_release"
    release: Release

    def execute(self) -> int:
        import subprocess
        from glob import glob as glob_fn

        tag = Tag.release_tag_name(
            self.release.package.name, self.release.release_version
        )
        dist_name = self.release.package.name.replace("-", "_")
        dist_pattern = f"dist/{dist_name}-{self.release.release_version.raw}-*.whl"

        files = sorted(glob_fn(dist_pattern))
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
        from glob import glob as glob_fn

        dist_name = self.release.package.name.replace("-", "_")
        dist_pattern = f"dist/{dist_name}-{self.release.release_version.raw}-*.whl"

        files = sorted(glob_fn(dist_pattern))
        args = ["uv", "publish"]
        if self.publishing.index:
            args.extend(["--index", self.publishing.index])
        if self.publishing.trusted_publishing:
            args.extend(["--trusted-publishing", self.publishing.trusted_publishing])
        args.extend(files)
        return subprocess.run(args).returncode


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
        runner_json = os.environ.get("UVR_RUNNER", "")
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


AnyCommand = Annotated[
    Union[
        ShellCommand,
        CreateTagCommand,
        SetVersionCommand,
        PinDepsCommand,
        CreateReleaseCommand,
        PublishToIndexCommand,
        BuildCommand,
        DownloadWheelsCommand,
        CommandGroup,
    ],
    Discriminator("type"),
]
