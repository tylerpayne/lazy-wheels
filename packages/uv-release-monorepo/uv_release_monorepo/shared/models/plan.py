"""Plan and package models for uv-release-monorepo.

These Pydantic models represent the core data structures used throughout
the release pipeline.
"""

from __future__ import annotations

import json as _json
import subprocess
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol, Union

from packaging.utils import canonicalize_name
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    computed_field,
    model_validator,
)


def _validate_runner_key(v: Any) -> tuple[str, ...]:
    """Parse a runner key from a JSON string or sequence into a tuple."""
    if isinstance(v, str):
        parsed = _json.loads(v)
        if not isinstance(parsed, list):
            msg = f"Expected JSON array for runner key, got {type(parsed).__name__}"
            raise ValueError(msg)
        return tuple(parsed)
    if isinstance(v, (list, tuple)):
        return tuple(v)
    msg = f"Expected str, list, or tuple for runner key, got {type(v).__name__}"
    raise ValueError(msg)


RunnerKey = Annotated[
    tuple[str, ...],
    PlainValidator(_validate_runner_key),
    PlainSerializer(lambda v: _json.dumps(list(v)), return_type=str),
]
"""Runner label key: a tuple of runner labels (e.g. ``("ubuntu-latest",)``).

Accepts JSON strings (``'["ubuntu-latest"]'``), lists, or tuples on input.
Serializes back to a JSON string for use as a dict key in JSON output.
"""


def _dist_name(name: str) -> str:
    """Convert a package name to its wheel/dist filename stem."""
    return canonicalize_name(name).replace("-", "_")


# ---------------------------------------------------------------------------
# Command protocol + implementations
# ---------------------------------------------------------------------------


class Command(Protocol):
    """Interface for executable release-plan commands."""

    label: str
    check: bool

    def execute(self) -> subprocess.CompletedProcess[bytes]: ...


@dataclass
class PlanConfig:
    """Configuration for ReleasePlanner.

    Groups the parameters needed to generate a release plan. Uses dataclass
    rather than BaseModel because this is internal configuration, not
    serialized data.

    Attributes:
        rebuild_all: If True, mark all packages as changed.
        matrix: Per-package runner configuration from the workflow file.
        uvr_version: The uvr version to embed in the plan.
        python_version: Python version for CI builds.
        ci_publish: If True (default), plan targets CI execution.
        release_type: One of "final", "minor", "major", "dev", "pre", "post".
        dry_run: If True, skip local writes (version bumps, dep pins).
    """

    rebuild_all: bool
    matrix: dict[str, list[list[str]]]
    uvr_version: str
    python_version: str = "3.12"
    ci_publish: bool = True
    release_type: str = "final"
    dry_run: bool = False


class PackageInfo(BaseModel):
    """Metadata for a single package in the monorepo workspace.

    Attributes:
        path: Relative path from workspace root to the package directory.
        version: Current version string from pyproject.toml.
        deps: List of internal (workspace) dependency names. External deps
              are not tracked here since we only need to manage internal
              version pinning.
    """

    path: str
    version: str
    deps: list[str] = Field(default_factory=list)


class ChangedPackage(PackageInfo):
    """A package that has changed and will be released.

    Extends PackageInfo with version lifecycle information and runner
    configuration needed for CI.

    Attributes:
        current_version: Version in pyproject.toml before any changes.
        release_version: Version that will be published.
        next_version: Post-release dev version to bump to after release.
        last_release_tag: Most recent GitHub release tag, or None.
        release_notes: Markdown release notes for this package.
        make_latest: Whether this package's release should be marked "Latest".
        runners: Runner label sets for build matrix.
    """

    current_version: str
    release_version: str
    next_version: str = ""
    last_release_tag: str | None = None
    release_notes: str = ""
    make_latest: bool = False
    runners: list[list[str]] = Field(default_factory=lambda: [["ubuntu-latest"]])


class ShellCommand(BaseModel):
    """A single shell command in the release plan.

    The planner pre-computes every command; the executor runs them
    via ``execute()``.

    Attributes:
        type: Discriminator for the command union.
        args: Command and arguments, e.g. ``["git", "tag", "pkg/v1.0.0"]``.
        label: Human-readable description printed before execution.
        check: If True, abort on non-zero exit code.
    """

    type: Literal["shell"] = "shell"
    args: list[str]
    label: str = ""
    check: bool = True

    def execute(self) -> subprocess.CompletedProcess[bytes]:
        """Run the command via subprocess."""
        return subprocess.run(self.args)


# Backwards-compatible alias for user hooks that import PlanCommand.
PlanCommand = ShellCommand


class FetchGithubReleaseCommand(BaseModel):
    """Download platform-compatible wheels from a GitHub release.

    At execution time, queries the release for available assets, prefers
    universal (``py3-none-any``) wheels, and falls back to platform-filtered
    downloads using ``packaging.tags.sys_tags()``.

    Attributes:
        type: Discriminator for the command union.
        tag: GitHub release tag to download from (e.g. ``"pkg/v1.0.0"``).
        dist_name: Wheel distribution name prefix (e.g. ``"pkg_alpha"``).
        directory: Local directory to download wheels into.
        label: Human-readable description printed before execution.
        check: If True, abort on non-zero exit code.
    """

    type: Literal["fetch_release"] = "fetch_release"
    tag: str
    dist_name: str
    directory: str = "deps"
    label: str = ""
    check: bool = True

    def execute(self) -> subprocess.CompletedProcess[bytes]:
        """Query release assets and download only compatible wheels."""
        from packaging.tags import sys_tags
        from packaging.utils import parse_wheel_filename

        # 1. List release assets
        result = subprocess.run(
            ["gh", "release", "view", self.tag, "--json", "assets"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return subprocess.CompletedProcess(args=[], returncode=1)

        assets = _json.loads(result.stdout).get("assets", [])
        wheel_names = [
            a["name"]
            for a in assets
            if a["name"].startswith(f"{self.dist_name}-") and a["name"].endswith(".whl")
        ]

        if not wheel_names:
            return subprocess.CompletedProcess(args=[], returncode=1)

        # 2. Prefer universal wheels (platform == "any")
        universal = [
            name
            for name in wheel_names
            if any(t.platform == "any" for t in parse_wheel_filename(name)[3])
        ]

        if universal:
            to_download = universal
        else:
            # 3. Filter for platform-compatible wheels
            compatible = set(sys_tags())
            to_download = [
                name
                for name in wheel_names
                if parse_wheel_filename(name)[3] & compatible
            ]

        if not to_download:
            return subprocess.CompletedProcess(args=[], returncode=1)

        # 4. Download with exact filenames as patterns
        args = [
            "gh",
            "release",
            "download",
            self.tag,
            "--dir",
            self.directory,
            "--clobber",
        ]
        for name in to_download:
            args.extend(["--pattern", name])

        return subprocess.run(args)


class FetchRunArtifactsCommand(BaseModel):
    """Download platform-compatible wheels from a GitHub Actions run's artifacts.

    At execution time, downloads artifacts matching ``wheels-*`` from the run,
    then filters for wheels compatible with the current platform — preferring
    universal (``py3-none-any``) wheels.

    Attributes:
        type: Discriminator for the command union.
        run_id: GitHub Actions run ID to download artifacts from.
        dist_name: Wheel distribution name prefix (e.g. ``"pkg_alpha"``).
        directory: Local directory to save compatible wheels into.
        label: Human-readable description printed before execution.
        check: If True, abort on non-zero exit code.
    """

    type: Literal["fetch_run_artifacts"] = "fetch_run_artifacts"
    run_id: str
    dist_name: str
    directory: str = "dist"
    label: str = ""
    check: bool = True

    def execute(self) -> subprocess.CompletedProcess[bytes]:
        """Download run artifacts and extract compatible wheels."""
        import shutil
        import tempfile

        from packaging.tags import sys_tags
        from packaging.utils import parse_wheel_filename

        # 1. Download artifacts into a temp dir (gh extracts into subdirs)
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    "gh",
                    "run",
                    "download",
                    self.run_id,
                    "--pattern",
                    "wheels-*",
                    "--dir",
                    tmp,
                ],
            )
            if result.returncode != 0:
                return result

            # 2. Glob all matching wheels from artifact subdirs
            from pathlib import Path

            all_wheels = list(Path(tmp).rglob(f"{self.dist_name}-*.whl"))
            if not all_wheels:
                return subprocess.CompletedProcess(args=[], returncode=1)

            # 3. Prefer universal wheels (platform == "any")
            universal = [
                whl
                for whl in all_wheels
                if any(t.platform == "any" for t in parse_wheel_filename(whl.name)[3])
            ]

            if universal:
                to_copy = universal
            else:
                # 4. Filter for platform-compatible wheels
                compatible = set(sys_tags())
                to_copy = [
                    whl
                    for whl in all_wheels
                    if parse_wheel_filename(whl.name)[3] & compatible
                ]

            if not to_copy:
                return subprocess.CompletedProcess(args=[], returncode=1)

            # 5. Copy compatible wheels to output directory
            Path(self.directory).mkdir(parents=True, exist_ok=True)
            for whl in to_copy:
                shutil.copy2(whl, self.directory)

        return subprocess.CompletedProcess(args=[], returncode=0)


StageCommand = Annotated[
    Union[ShellCommand, FetchGithubReleaseCommand, FetchRunArtifactsCommand],
    Field(discriminator="type"),
]
"""Union of command types that can appear in a build stage's setup list."""


class BuildStage(BaseModel):
    """A group of per-package command sequences that execute concurrently.

    Stages execute sequentially (layer 0 completes before layer 1 starts).
    Within a stage, each package's commands run in a separate thread so
    independent packages build in parallel.

    Attributes:
        setup: Commands that run sequentially before parallel builds.
        packages: Map of package name to its command list.  Different
            packages run concurrently; commands within a package run
            sequentially.
        cleanup: Commands that run sequentially after parallel builds.
    """

    setup: list[StageCommand] = Field(default_factory=list)
    packages: dict[str, list[ShellCommand]] = Field(default_factory=dict)
    cleanup: list[ShellCommand] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _default_command_types(cls, data: Any) -> Any:
        """Add ``type='shell'`` to commands missing the discriminator.

        Provides backwards compatibility with plans serialized before
        the ``type`` field was introduced.
        """
        if isinstance(data, dict):
            for cmd in data.get("setup", []):
                if isinstance(cmd, dict) and "type" not in cmd:
                    cmd["type"] = "shell"
        return data


class ReleasePlan(BaseModel):
    """Self-contained release plan generated locally and executed by CI.

    Contains everything the executor workflow needs: which packages changed,
    what their last release tags were, which runners to use for each build,
    and the pre-computed commands. The executor never needs to run git
    commands, change detection, or version arithmetic.

    Extra keys are allowed (``extra="allow"``) so that user hooks can attach
    custom data that travels through the pipeline to CI.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: int = 10
    uvr_version: str
    uvr_install: str = "uv-release-monorepo"
    python_version: str = "3.12"
    release_type: str = "final"
    rebuild_all: bool
    ci_publish: bool = False
    changed: dict[str, ChangedPackage]
    unchanged: dict[str, PackageInfo]
    skip: list[str] = Field(default_factory=list)
    reuse_run_id: str = ""

    # Pre-computed command sequences for the executor
    build_commands: dict[RunnerKey, list[BuildStage]] = Field(default_factory=dict)
    release_commands: list[ShellCommand] = Field(default_factory=list)
    finalize_commands: list[ShellCommand] = Field(default_factory=list)

    @model_validator(mode="after")
    def _forbid_skip_validate(self) -> ReleasePlan:
        if "uvr-validate" in self.skip:
            msg = "uvr-validate cannot be skipped"
            raise ValueError(msg)
        return self

    @computed_field
    @property
    def build_matrix(self) -> list[list[str]]:
        """Unique runner label sets across all changed packages.

        Used by GitHub Actions ``strategy.matrix`` to fan out build jobs.
        """
        seen: set[tuple[str, ...]] = set()
        result: list[list[str]] = []
        for pkg in self.changed.values():
            for runner in pkg.runners:
                key = tuple(runner)
                if key not in seen:
                    seen.add(key)
                    result.append(runner)
        return sorted(result)

    @computed_field
    @property
    def release_matrix(self) -> list[dict[str, Any]]:
        """Publish matrix entries for GitHub Actions ``strategy.matrix.include``.

        Each entry contains all fields needed by the ``softprops/action-gh-release``
        action: tag, title, body, file pattern, and make_latest flag.
        """
        entries: list[dict[str, Any]] = []
        for name, pkg in sorted(self.changed.items()):
            entries.append(
                {
                    "package": name,
                    "version": pkg.release_version,
                    "tag": f"{name}/v{pkg.release_version}",
                    "title": f"{name} {pkg.release_version}",
                    "body": pkg.release_notes,
                    "make_latest": pkg.make_latest,
                    "dist_name": _dist_name(name),
                }
            )
        return entries
