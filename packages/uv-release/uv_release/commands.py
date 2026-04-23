"""All command types. Each command is frozen and knows how to execute itself."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import Discriminator, Field

from .types import (
    Command,
    CommandGroup,
    Package,
    PackagePyProjectDoc,
    Publishing,
    Release,
    Tag,
    Version,
)

_UVR_RUNNER_ENV = "UVR_RUNNER"


class ShellCommand(Command):
    """Run a subprocess."""

    type: Literal["shell"] = "shell"
    args: list[str]

    def execute(self) -> int:
        import subprocess

        result = subprocess.run(self.args)
        return result.returncode


class CreateTagCommand(Command):
    """Create a git tag via subprocess.

    Uses ``git tag`` so the tag is visible to ``git push --follow-tags``.
    """

    type: Literal["create_tag"] = "create_tag"
    tag_name: str

    def execute(self) -> int:
        import subprocess

        subprocess.run(
            ["git", "tag", self.tag_name],
            check=True,
        )
        return 0


class SetVersionCommand(Command):
    """Set [project].version in a package's pyproject.toml."""

    type: Literal["set_version"] = "set_version"
    package: Package
    version: Version

    def execute(self) -> int:
        path = f"{self.package.path}/pyproject.toml"
        doc = PackagePyProjectDoc.read(path)
        doc.version = self.version.raw
        doc.write(path)
        return 0


class PinDepsCommand(Command):
    """Pin internal dependency versions in a package's pyproject.toml."""

    type: Literal["pin_deps"] = "pin_deps"
    package: Package
    pins: dict[str, Package]

    def execute(self) -> int:
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name

        path = f"{self.package.path}/pyproject.toml"
        doc = PackagePyProjectDoc.read(path)

        for dep_list in (doc.dependencies, doc.build_requires):
            for i, dep in enumerate(dep_list):
                req = Requirement(str(dep))
                name = canonicalize_name(req.name)
                if name in self.pins:
                    pinned = self.pins[name]
                    lower = pinned.version.raw
                    upper = pinned.version.bump_minor().raw
                    dep_list[i] = f"{req.name}>={lower},<{upper}"

        doc.write(path)
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
        dist_name = self.release.package.dist_name
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

        dist_name = self.release.package.dist_name
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


class MakeDirectoryCommand(Command):
    """Create a directory, including parent directories."""

    type: Literal["make_directory"] = "make_directory"
    path: str

    def execute(self) -> int:
        from pathlib import Path

        Path(self.path).mkdir(parents=True, exist_ok=True)
        return 0


class WriteFileCommand(Command):
    """Write content to a file, creating parent directories as needed."""

    type: Literal["write_file"] = "write_file"
    path: str
    content: str

    def execute(self) -> int:
        from pathlib import Path

        dest = Path(self.path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(self.content, encoding="utf-8")
        return 0


class UpdateTomlCommand(Command):
    """Update a key in [tool.uvr.config] of the root pyproject.toml."""

    type: Literal["update_toml"] = "update_toml"
    key: str
    value: Any

    def execute(self) -> int:
        import tomlkit
        from pathlib import Path

        path = Path("pyproject.toml")
        if not path.exists():
            return 1
        doc = tomlkit.loads(path.read_text())
        tool = doc.setdefault("tool", {})
        uvr = tool.setdefault("uvr", {})
        config = uvr.setdefault("config", {})
        config[self.key] = self.value
        path.write_text(tomlkit.dumps(doc))
        return 0


class WriteUvrSectionCommand(Command):
    """Write a complete section under [tool.uvr] in root pyproject.toml."""

    type: Literal["write_uvr_section"] = "write_uvr_section"
    section: str
    data: Any

    def execute(self) -> int:
        import tomlkit
        from pathlib import Path

        path = Path("pyproject.toml")
        if not path.exists():
            return 1
        doc = tomlkit.loads(path.read_text())
        tool = doc.setdefault("tool", {})
        uvr = tool.setdefault("uvr", {})
        uvr[self.section] = self.data
        path.write_text(tomlkit.dumps(doc))
        return 0


class DispatchWorkflowCommand(Command):
    """Dispatch a release plan to GitHub Actions."""

    type: Literal["dispatch_workflow"] = "dispatch_workflow"
    plan_json: str
    workflow: str = "release.yml"

    def execute(self) -> int:
        import subprocess

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
        )
        ref = result.stdout.strip() if result.returncode == 0 else "main"

        return subprocess.run(
            [
                "gh",
                "workflow",
                "run",
                self.workflow,
                "--ref",
                ref,
                "-f",
                f"plan={self.plan_json}",
            ],
        ).returncode


class MergeUpgradeCommand(Command):
    """Three-way merge of a file with interactive conflict resolution.

    Reads the current file, merges with base and fresh versions, writes the result.
    If conflicts remain, opens an editor and offers to revert.
    """

    type: Literal["merge_upgrade"] = "merge_upgrade"
    dest_path: str
    base_text: str
    fresh_text: str
    editor: str = ""

    def execute(self) -> int:
        import subprocess
        from pathlib import Path

        from .merge import parse_editor_command, merge_texts

        dest = Path(self.dest_path)
        existing_text = dest.read_text()

        merged_text, has_conflicts = merge_texts(
            existing_text, self.base_text, self.fresh_text
        )

        if merged_text.rstrip() == existing_text.rstrip():
            print(f"  {self.dest_path}: already up to date")
            return 0

        dest.write_text(merged_text)

        if not (has_conflicts or "<<<<<<" in merged_text):
            print(f"  {self.dest_path}: merged cleanly")
            return 0

        # Conflicts: interactive resolution
        print(f"  {self.dest_path}: merged with conflicts")
        if self.editor:
            prompt = f"  Open in {self.editor} to resolve? [Y/n] "
        else:
            prompt = "  Resolve conflicts manually, then press Enter. [n to skip] "

        try:
            answer = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        if self.editor and answer not in ("n", "no"):
            subprocess.run([*parse_editor_command(self.editor), str(dest)])

        if "<<<<<<" in dest.read_text():
            print("  Unresolved conflicts remain.")
            try:
                revert = input("  Revert to original? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                revert = ""
            if revert not in ("n", "no"):
                dest.write_text(existing_text)
                print("  Reverted.")
                return 1

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
        MakeDirectoryCommand,
        WriteFileCommand,
        UpdateTomlCommand,
        WriteUvrSectionCommand,
        DispatchWorkflowCommand,
        MergeUpgradeCommand,
        CommandGroup,
    ],
    Discriminator("type"),
]
