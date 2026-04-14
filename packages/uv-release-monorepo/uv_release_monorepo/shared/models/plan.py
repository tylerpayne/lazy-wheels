"""Plan and package models for uv-release.

These Pydantic models represent the core data structures used throughout
the release pipeline.
"""

from __future__ import annotations

import json as _json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol, Union

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
        v = " ".join(v.split())  # normalize multiline JSON from toJSON()
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
        restrict_packages: Restrict build scope to these packages and their
            transitive dependencies. Packages outside the closure become
            unchanged.
        dev_release: If True, publish .devN versions as-is (``--dev`` mode).
        dry_run: If True, skip local writes (version bumps, dep pins).
        release_notes: Per-package release notes overrides (name → markdown).
    """

    rebuild_all: bool
    matrix: dict[str, list[list[str]]]
    uvr_version: str
    python_version: str = "3.12"
    rebuild: list[str] = field(default_factory=list)
    restrict_packages: list[str] = field(default_factory=list)
    skip: set[str] = field(default_factory=set)
    ci_publish: bool = True
    dev_release: bool = False
    dry_run: bool = False
    release_notes: dict[str, str] = field(default_factory=dict)


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
            True = force latest, False = force not latest, None = let gh decide.
        runners: Runner label sets for build matrix.
    """

    current_version: str
    release_version: str
    next_version: str = ""
    last_release_tag: str | None = None
    baseline_tag: str | None = None
    release_notes: str = ""
    make_latest: bool | None = None
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
    gh_repo: str = ""
    label: str = ""
    check: bool = True

    def execute(self) -> subprocess.CompletedProcess[bytes]:
        """Query release assets and download only compatible wheels."""
        from packaging.tags import sys_tags
        from packaging.utils import parse_wheel_filename

        # 1. List release assets
        view_cmd = ["gh", "release", "view", self.tag, "--json", "assets"]
        if self.gh_repo:
            view_cmd.extend(["--repo", self.gh_repo])
        result = subprocess.run(view_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(
                f"ERROR: Could not find release {self.tag}: {result.stderr.strip()}",
                file=sys.stderr,
            )
            return subprocess.CompletedProcess(args=[], returncode=1)

        assets = _json.loads(result.stdout).get("assets", [])
        wheel_names = [
            a["name"]
            for a in assets
            if a["name"].startswith(f"{self.dist_name}-") and a["name"].endswith(".whl")
        ]

        if not wheel_names:
            all_names = [a["name"] for a in assets]
            print(
                f"ERROR: Release {self.tag} has no wheels for {self.dist_name}. "
                f"Assets: {all_names or '(none)'}",
                file=sys.stderr,
            )
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
            print(
                f"ERROR: No platform-compatible wheels in {self.tag}. "
                f"Available: {wheel_names}",
                file=sys.stderr,
            )
            return subprocess.CompletedProcess(args=[], returncode=1)

        # 4. Download with exact filenames as patterns
        dl_cmd = [
            "gh",
            "release",
            "download",
            self.tag,
            "--dir",
            self.directory,
            "--clobber",
        ]
        if self.gh_repo:
            dl_cmd.extend(["--repo", self.gh_repo])
        for name in to_download:
            dl_cmd.extend(["--pattern", name])

        return subprocess.run(dl_cmd)


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
    gh_repo: str = ""
    all_platforms: bool = False
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
            dl_cmd = [
                "gh",
                "run",
                "download",
                self.run_id,
                "--pattern",
                "wheels-*",
                "--dir",
                tmp,
            ]
            if self.gh_repo:
                dl_cmd.extend(["--repo", self.gh_repo])
            result = subprocess.run(dl_cmd)
            if result.returncode != 0:
                return result

            # 2. Glob all matching wheels from artifact subdirs
            from pathlib import Path

            pattern = f"{self.dist_name}-*.whl" if self.dist_name else "*.whl"
            all_wheels = list(Path(tmp).rglob(pattern))
            if not all_wheels:
                return subprocess.CompletedProcess(args=[], returncode=1)

            if self.all_platforms:
                # Release job: keep all wheels for all platforms
                to_copy = all_wheels
            else:
                # Build/install: filter to current platform
                compatible = set(sys_tags())
                to_copy: list[Path] = []
                by_dist: dict[str, list[Path]] = {}
                for whl in all_wheels:
                    dist = whl.name.split("-")[0]
                    by_dist.setdefault(dist, []).append(whl)

                for dist, dist_wheels in by_dist.items():
                    uni = [
                        w
                        for w in dist_wheels
                        if any(
                            t.platform == "any" for t in parse_wheel_filename(w.name)[3]
                        )
                    ]
                    if uni:
                        to_copy.extend(uni)
                    else:
                        to_copy.extend(
                            w
                            for w in dist_wheels
                            if parse_wheel_filename(w.name)[3] & compatible
                        )

            if not to_copy:
                return subprocess.CompletedProcess(args=[], returncode=1)

            # 5. Copy compatible wheels to output directory
            Path(self.directory).mkdir(parents=True, exist_ok=True)
            for whl in to_copy:
                shutil.copy2(whl, self.directory)

        return subprocess.CompletedProcess(args=[], returncode=0)


class PublishGithubReleaseCommand(BaseModel):
    """Create a GitHub release and upload matching wheel files.

    At execution time, resolves ``dist_pattern`` via ``glob.glob()`` to find
    built wheels, then creates a GitHub release with ``gh release create``.
    Uses ``--target`` with the current HEAD SHA so the release tag points to
    the correct commit even if it hasn't been pushed yet.

    Attributes:
        type: Discriminator for the command union.
        tag: Release tag (e.g. ``"pkg-alpha/v1.0.0"``).
        title: Human-readable release title.
        notes: Markdown release notes body.
        dist_pattern: Glob pattern for wheel files (e.g. ``"dist/pkg_alpha-1.0.0-*.whl"``).
        make_latest: Whether to mark this release as "Latest" on GitHub.
        label: Human-readable description printed before execution.
        check: If True, abort on non-zero exit code.
    """

    type: Literal["publish_release"] = "publish_release"
    tag: str
    title: str
    notes: str
    dist_pattern: str
    make_latest: bool | None = None
    label: str = ""
    check: bool = True

    def execute(self) -> subprocess.CompletedProcess[bytes]:
        """Create a GitHub release, uploading wheels matching dist_pattern."""
        from glob import glob as glob_fn

        # Resolve HEAD so --target pins the tag to the correct commit
        sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        target = sha_result.stdout.strip() if sha_result.returncode == 0 else "HEAD"

        files = sorted(glob_fn(self.dist_pattern))
        if not files:
            print(
                f"ERROR: No files matching {self.dist_pattern!r} — "
                f"cannot create release {self.tag} without assets.",
                file=sys.stderr,
            )
            return subprocess.CompletedProcess(args=[], returncode=1)
        args = [
            "gh",
            "release",
            "create",
            self.tag,
            "--target",
            target,
            "--title",
            self.title,
            "--notes",
            self.notes,
        ]
        if self.make_latest is True:
            args.append("--latest")
        elif self.make_latest is False:
            args.append("--latest=false")
        args.extend(files)
        return subprocess.run(args)


class DownloadWheelsCommand(BaseModel):
    """Smart wheel fetcher: run artifacts → release fallback, with transitive deps.

    At execution time, for each package in ``packages``:

    1. Check ``directory`` for a cached wheel (skip if found).
    2. If ``run_id`` is set, download all run artifacts into ``directory``.
    3. Fall back to the latest GitHub release for the package.
    4. Parse the wheel's ``METADATA`` for internal deps and fetch those too.

    Packages in ``exclude`` are skipped (they'll be built, not fetched).

    Attributes:
        type: Discriminator for the command union.
        packages: Map of package name → release tag (e.g. ``{"pkg": "pkg/v1.0"}``)
            for fallback. Tag may be empty if no release exists.
        exclude: Package names to skip (changed packages that will be built).
        gh_repo: GitHub ``ORG/REPO`` for API calls.
        run_id: If set, try downloading from this CI run first.
        directory: Local directory to save wheels into.
        label: Human-readable description printed before execution.
        check: If True, abort on non-zero exit code.
    """

    type: Literal["download_wheels"] = "download_wheels"
    packages: dict[str, str]  # name → release tag
    exclude: list[str] = Field(default_factory=list)
    gh_repo: str = ""
    run_id: str = ""
    all_platforms: bool = False
    directory: str = "deps"
    label: str = ""
    check: bool = True

    def execute(self) -> subprocess.CompletedProcess[bytes]:
        """Fetch wheels with run-id → release fallback and transitive resolution."""
        from pathlib import Path
        from zipfile import ZipFile

        from packaging.metadata import Metadata
        from packaging.utils import canonicalize_name

        out = Path(self.directory)
        out.mkdir(parents=True, exist_ok=True)
        exclude = {canonicalize_name(n) for n in self.exclude}

        # Known packages (for transitive dep detection)
        known = {canonicalize_name(n) for n in self.packages}

        # If run_id, download all artifacts upfront
        if self.run_id:
            print(f"  Downloading artifacts from run {self.run_id}...")
            fetch = FetchRunArtifactsCommand(
                run_id=self.run_id,
                dist_name="",  # all wheels
                gh_repo=self.gh_repo,
                all_platforms=self.all_platforms,
                directory=str(out),
            )
            fetch.execute()  # best-effort; missing packages fall back to releases

        # BFS fetch
        to_fetch = list(self.packages.keys())
        fetched: set[str] = set()

        while to_fetch:
            pkg = to_fetch.pop(0)
            canon = canonicalize_name(pkg)
            if canon in fetched or canon in exclude:
                continue
            fetched.add(canon)

            dist_name = canon.replace("-", "_")

            # Check if already in output dir (from run artifacts or prior fetch)
            cached = sorted(out.glob(f"{dist_name}-*.whl"))
            if cached:
                whl = cached[-1]
                print(f"  {pkg}: {whl.name} (cached)")
            else:
                # Fall back to GitHub release
                tag = self.packages.get(pkg, "")
                if not tag:
                    print(f"  {pkg}: no release tag, skipping", file=sys.stderr)
                    continue

                release_fetch = FetchGithubReleaseCommand(
                    tag=tag,
                    dist_name=dist_name,
                    gh_repo=self.gh_repo,
                    directory=str(out),
                )
                result = release_fetch.execute()
                if result.returncode != 0:
                    print(f"  {pkg}: download failed, skipping", file=sys.stderr)
                    continue

                found = sorted(out.glob(f"{dist_name}-*.whl"))
                if not found:
                    continue
                whl = found[-1]
                print(f"  {pkg}: {whl.name}")

            # Resolve transitive deps from wheel metadata
            try:
                with ZipFile(whl) as zf:
                    for entry in zf.namelist():
                        if entry.endswith(".dist-info/METADATA"):
                            meta = Metadata.from_email(zf.read(entry))
                            for req in meta.requires_dist or []:
                                if req.marker and "extra" in str(req.marker):
                                    continue
                                dep = canonicalize_name(req.name)
                                if dep in known and dep not in fetched:
                                    to_fetch.append(dep)
                            break
            except Exception:
                pass

        return subprocess.CompletedProcess(args=[], returncode=0)


StageCommand = Annotated[
    Union[
        ShellCommand,
        FetchGithubReleaseCommand,
        FetchRunArtifactsCommand,
        DownloadWheelsCommand,
    ],
    Field(discriminator="type"),
]
"""Union of command types that can appear in a build stage's setup list."""


class PinDepsCommand(BaseModel):
    """Pin internal dependency versions in a pyproject.toml.

    Calls ``pin_dependencies()`` directly rather than shelling out to a
    CLI subprocess.

    Attributes:
        type: Discriminator for the command union.
        path: Path to the pyproject.toml file to update.
        versions: Map of dependency name to pinned version.
        label: Human-readable description printed before execution.
        check: If True, abort on non-zero exit code.
    """

    type: Literal["pin_deps"] = "pin_deps"
    path: str
    versions: dict[str, str]
    label: str = ""
    check: bool = True

    def execute(self) -> subprocess.CompletedProcess[bytes]:
        """Pin dependencies in the target pyproject.toml."""
        from pathlib import Path

        from ..utils.dependencies import pin_dependencies

        pin_dependencies(Path(self.path), self.versions)
        return subprocess.CompletedProcess(args=[], returncode=0)


ReleaseCommand = Annotated[
    Union[ShellCommand, PublishGithubReleaseCommand],
    Field(discriminator="type"),
]
"""Union of command types that can appear in the release commands list."""


class PublishToIndexCommand(BaseModel):
    """Publish wheel files to a package index using ``uv publish``.

    At execution time, resolves ``dist_pattern`` via ``glob.glob()`` to find
    built wheels, then uploads them with ``uv publish``.

    Attributes:
        type: Discriminator for the command union.
        dist_pattern: Glob pattern for wheel files (e.g. ``"dist/pkg_alpha-1.0.0-*.whl"``).
        index: Named index from ``[[tool.uv.index]]`` (``--index`` flag).
        trusted_publishing: OIDC mode: ``"automatic"``, ``"always"``, or ``"never"``.
        label: Human-readable description printed before execution.
        check: If True, abort on non-zero exit code.
    """

    type: Literal["publish_to_index"] = "publish_to_index"
    dist_pattern: str
    index: str = ""
    trusted_publishing: str = "automatic"
    label: str = ""
    check: bool = True

    def execute(self) -> subprocess.CompletedProcess[bytes]:
        """Upload matching files with ``uv publish``."""
        from glob import glob as glob_fn

        files = sorted(glob_fn(self.dist_pattern))
        if not files:
            print(
                f"ERROR: No files matching {self.dist_pattern!r} — "
                f"cannot publish to index.",
                file=sys.stderr,
            )
            return subprocess.CompletedProcess(args=[], returncode=1)

        args = ["uv", "publish"]
        if self.index:
            args.extend(["--index", self.index])
        if self.trusted_publishing:
            args.extend(["--trusted-publishing", self.trusted_publishing])
        args.extend(files)
        return subprocess.run(args)


PublishCommand = Annotated[
    Union[ShellCommand, PublishToIndexCommand],
    Field(discriminator="type"),
]
"""Union of command types that can appear in the publish commands list."""


BumpCommand = Annotated[
    Union[ShellCommand, PinDepsCommand],
    Field(discriminator="type"),
]
"""Union of command types that can appear in the bump commands list."""


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

    schema_version: int = 12
    uvr_version: str
    uvr_install: str = "uv-release"
    python_version: str = "3.12"
    dev_release: bool = False
    rebuild_all: bool
    ci_publish: bool = False
    changed: dict[str, ChangedPackage]
    unchanged: dict[str, PackageInfo]
    skip: list[str] = Field(default_factory=list)
    reuse_run_id: str = ""

    # Pre-computed command sequences for the executor
    build_commands: dict[RunnerKey, list[BuildStage]] = Field(default_factory=dict)
    release_commands: list[ReleaseCommand] = Field(default_factory=list)
    publish_commands: list[PublishCommand] = Field(default_factory=list)
    publish_environment: str = ""
    bump_commands: list[BumpCommand] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_and_default(cls, data: Any) -> Any:
        """Backwards-compatibility migrations for older plan JSON.

        - Convert legacy ``release_type`` string to ``dev_release`` bool.
        - Add ``type='shell'`` to commands missing the discriminator.
        """
        if isinstance(data, dict):
            # Migrate release_type → dev_release (schema ≤10)
            if "release_type" in data and "dev_release" not in data:
                data["dev_release"] = data.pop("release_type") == "dev"

            for key in ("release_commands", "bump_commands"):
                for cmd in data.get(key, []):
                    if isinstance(cmd, dict) and "type" not in cmd:
                        cmd["type"] = "shell"
        return data

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
