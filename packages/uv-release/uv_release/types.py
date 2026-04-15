"""All frozen entity types for the uv_release pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from packaging.version import Version as PkgVersion
from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, field_validator


# ---------------------------------------------------------------------------
# VersionState enum
# ---------------------------------------------------------------------------


class VersionState(Enum):
    """The 11 distinct version forms a package can be in."""

    CLEAN_STABLE = "X.Y.Z"
    DEV0_STABLE = "X.Y.Z.dev0"
    DEVK_STABLE = "X.Y.Z.devK"
    CLEAN_PRE0 = "X.Y.Za0"
    CLEAN_PREN = "X.Y.ZaN"
    DEV0_PRE = "X.Y.ZaN.dev0"
    DEVK_PRE = "X.Y.ZaN.devK"
    CLEAN_POST0 = "X.Y.Z.post0"
    CLEAN_POSTM = "X.Y.Z.postM"
    DEV0_POST = "X.Y.Z.postM.dev0"
    DEVK_POST = "X.Y.Z.postM.devK"


# ---------------------------------------------------------------------------
# BumpType enum
# ---------------------------------------------------------------------------


class BumpType(Enum):
    """Bump type for standalone version bumping."""

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    ALPHA = "alpha"
    BETA = "beta"
    RC = "rc"
    POST = "post"
    DEV = "dev"
    STABLE = "stable"


# ---------------------------------------------------------------------------
# PLAN PARAMS
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanParams:
    """CLI flags passed to every pipeline step. Frozen."""

    rebuild_all: bool = False
    rebuild: frozenset[str] = frozenset()
    restrict_packages: frozenset[str] = frozenset()
    dev_release: bool = False
    dry_run: bool = False
    skip: frozenset[str] = frozenset()
    release_notes: dict[str, str] | None = None
    bump_type: BumpType = BumpType.DEV
    pin: bool = True
    commit: bool = True
    push: bool = True
    tag: bool = True
    target: Literal["ci", "local"] = "local"
    require_clean_worktree: bool = True


# ---------------------------------------------------------------------------
# VERSION
# ---------------------------------------------------------------------------

# Canonical pre-release kind strings from packaging
_PRE_KIND_MAP: dict[str, str] = {
    "a": "a",
    "alpha": "a",
    "b": "b",
    "beta": "b",
    "rc": "rc",
    "c": "rc",
}


class Version(BaseModel):
    """A PEP 440 version, parsed once into structured fields.

    Wraps packaging.version.Version for parsing and comparison.
    All fields are derived from the parsed version at construction time.
    """

    model_config = ConfigDict(frozen=True)

    raw: str
    state: VersionState
    major: int
    minor: int
    patch: int
    is_dev: bool
    dev_number: int | None = None
    pre_kind: str | None = None
    pre_number: int | None = None
    post_number: int | None = None

    @property
    def base(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    # --- Construction ---

    @staticmethod
    def parse(raw: str) -> Version:
        """Parse a PEP 440 version string into a frozen Version."""
        pv = PkgVersion(raw)  # raises InvalidVersion

        pre_kind: str | None = None
        pre_number: int | None = None
        if pv.pre is not None:
            pre_kind = _PRE_KIND_MAP.get(pv.pre[0], pv.pre[0])
            pre_number = pv.pre[1]
        post_number = pv.post if pv.post is not None else None
        dev_number = pv.dev if pv.dev is not None else None
        is_dev = dev_number is not None

        state = Version._classify(pre_kind, pre_number, post_number, dev_number)

        return Version(
            raw=str(pv),
            state=state,
            major=pv.major,
            minor=pv.minor,
            patch=pv.micro,
            is_dev=is_dev,
            dev_number=dev_number,
            pre_kind=pre_kind,
            pre_number=pre_number,
            post_number=post_number,
        )

    @staticmethod
    def build(
        base: str,
        *,
        pre_kind: str | None = None,
        pre_number: int | None = None,
        post_number: int | None = None,
        dev_number: int | None = None,
    ) -> Version:
        """Construct a Version from components. Delegates to packaging for normalization."""
        raw = base
        if pre_kind is not None:
            raw += f"{pre_kind}{pre_number if pre_number is not None else 0}"
        if post_number is not None:
            raw += f".post{post_number}"
        if dev_number is not None:
            raw += f".dev{dev_number}"

        # Round-trip through packaging for canonical form
        return Version.parse(raw)

    # --- Transformations (return new frozen Version) ---

    def with_dev(self, dev_number: int) -> Version:
        """Return a new Version with the given dev number."""
        return Version.build(
            self.base,
            pre_kind=self.pre_kind,
            pre_number=self.pre_number,
            post_number=self.post_number,
            dev_number=dev_number,
        )

    def without_dev(self) -> Version:
        """Return a new Version with the dev suffix stripped."""
        return Version.build(
            self.base,
            pre_kind=self.pre_kind,
            pre_number=self.pre_number,
            post_number=self.post_number,
        )

    def with_pre(self, kind: str, number: int) -> Version:
        """Return a new Version with the given pre-release kind and number."""
        return Version.build(self.base, pre_kind=kind, pre_number=number)

    def with_post(self, number: int) -> Version:
        """Return a new Version with the given post-release number."""
        return Version.build(self.base, post_number=number)

    def bump_major(self) -> Version:
        """Return a new base Version with major incremented, minor and patch reset."""
        return Version.build(f"{self.major + 1}.0.0")

    def bump_minor(self) -> Version:
        """Return a new base Version with minor incremented, patch reset."""
        return Version.build(f"{self.major}.{self.minor + 1}.0")

    def bump_patch(self) -> Version:
        """Return a new base Version with patch incremented."""
        return Version.build(f"{self.major}.{self.minor}.{self.patch + 1}")

    @staticmethod
    def _classify(
        pre_kind: str | None,
        pre_number: int | None,
        post_number: int | None,
        dev_number: int | None,
    ) -> VersionState:
        """Classify parsed version components into a VersionState."""
        has_pre = pre_kind is not None
        has_post = post_number is not None
        has_dev = dev_number is not None

        if has_post:
            if has_dev:
                assert dev_number is not None
                return (
                    VersionState.DEVK_POST if dev_number > 0 else VersionState.DEV0_POST
                )
            assert post_number is not None
            return (
                VersionState.CLEAN_POSTM
                if post_number > 0
                else VersionState.CLEAN_POST0
            )

        if has_pre:
            if has_dev:
                assert dev_number is not None
                return (
                    VersionState.DEVK_PRE if dev_number > 0 else VersionState.DEV0_PRE
                )
            assert pre_number is not None
            return (
                VersionState.CLEAN_PREN if pre_number > 0 else VersionState.CLEAN_PRE0
            )

        if has_dev:
            assert dev_number is not None
            return (
                VersionState.DEVK_STABLE if dev_number > 0 else VersionState.DEV0_STABLE
            )

        return VersionState.CLEAN_STABLE


# ---------------------------------------------------------------------------
# TAG
# ---------------------------------------------------------------------------


class Tag(BaseModel):
    """A git tag. Knows which package it belongs to."""

    model_config = ConfigDict(frozen=True)

    package_name: str
    raw: str
    version: Version
    is_baseline: bool
    commit: str

    @property
    def ref(self) -> str:
        """Full git ref: 'refs/tags/{raw}'."""
        return f"refs/tags/{self.raw}"

    @staticmethod
    def release_tag_name(package_name: str, version: Version) -> str:
        """Format a release tag name: '{package}/v{version}'."""
        return f"{package_name}/v{version.raw}"

    @staticmethod
    def baseline_tag_name(package_name: str, version: Version) -> str:
        """Format a baseline tag name: '{package}/v{version}-base'."""
        return f"{package_name}/v{version.raw}-base"

    @staticmethod
    def tag_prefix(package_name: str) -> str:
        """Tag prefix for a package: '{package}/v'."""
        return f"{package_name}/v"

    @staticmethod
    def is_baseline_tag_name(tag_name: str) -> bool:
        """Check if a tag name is a baseline tag."""
        return tag_name.endswith("-base")

    @staticmethod
    def parse_version_from_tag_name(tag_name: str) -> str:
        """Extract the version string from a tag name like 'pkg/v1.0.0' or 'pkg/v1.0.0-base'."""
        ver_str = tag_name.split("/v", 1)[1]
        if ver_str.endswith("-base"):
            ver_str = ver_str[:-5]
        return ver_str


# ---------------------------------------------------------------------------
# PACKAGE
# ---------------------------------------------------------------------------


class Package(BaseModel):
    """A package as discovered from pyproject.toml."""

    model_config = ConfigDict(frozen=True)

    name: str
    path: str
    version: Version
    deps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------


class Config(BaseModel):
    """Workspace configuration from [tool.uvr.config]."""

    model_config = ConfigDict(frozen=True)

    uvr_version: str
    latest_package: str = ""
    python_version: str = "3.12"
    include: frozenset[str] = frozenset()
    exclude: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# PUBLISHING
# ---------------------------------------------------------------------------


class Publishing(BaseModel):
    """Publishing configuration from [tool.uvr.publish]."""

    model_config = ConfigDict(frozen=True)

    index: str = ""
    environment: str = ""
    trusted_publishing: str = "automatic"
    include: frozenset[str] = frozenset()
    exclude: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# HOOKS
# ---------------------------------------------------------------------------


class Hooks:
    """User-provided release hooks. Loaded from disk by parse/hooks.py."""

    DEFAULT_FILE = "uvr_hooks.py"
    DEFAULT_CLASS = "Hooks"

    def pre_plan(self, params: PlanParams) -> PlanParams:
        return params

    def post_plan(self, plan: Plan) -> Plan:
        return plan

    def pre_build(self, plan: Plan, runner: list[str] | None = None) -> None:
        pass

    def post_build(self, plan: Plan, runner: list[str] | None = None) -> None:
        pass

    def pre_release(self, plan: Plan) -> None:
        pass

    def post_release(self, plan: Plan) -> None:
        pass

    def pre_publish(self, plan: Plan) -> None:
        pass

    def post_publish(self, plan: Plan) -> None:
        pass

    def pre_bump(self, plan: Plan) -> None:
        pass

    def post_bump(self, plan: Plan) -> None:
        pass


# ---------------------------------------------------------------------------
# WORKSPACE
# ---------------------------------------------------------------------------


class Workspace(BaseModel):
    """The workspace as parsed from disk. Frozen."""

    model_config = ConfigDict(frozen=True)

    packages: dict[str, Package]
    config: Config
    runners: dict[str, list[list[str]]]
    publishing: Publishing


# ---------------------------------------------------------------------------
# CHANGE
# ---------------------------------------------------------------------------


class Change(BaseModel):
    """A package that changed since its baseline. Produced by detect."""

    model_config = ConfigDict(frozen=True)

    package: Package
    baseline: Tag | None = None
    diff_stats: str | None = None
    commit_log: str = ""
    reason: str = ""


# ---------------------------------------------------------------------------
# RELEASE
# ---------------------------------------------------------------------------


class Release(BaseModel):
    """A changed package planned for release. Produced by plan."""

    model_config = ConfigDict(frozen=True)

    package: Package
    release_version: Version
    next_version: Version
    release_notes: str = ""
    make_latest: bool = False


# ---------------------------------------------------------------------------
# COMMAND (base)
# ---------------------------------------------------------------------------


class Command(BaseModel):
    """Base command. Subclasses in commands.py add a type discriminator and execute()."""

    model_config = ConfigDict(frozen=True)

    label: str = ""
    check: bool = True
    needs_user_confirmation: bool = False

    def execute(self) -> int:
        raise NotImplementedError


class CommandGroup(Command):
    """A container of commands executed under a single user confirmation prompt.

    When needs_user_confirmation=True, the executor prompts once for the whole group,
    then runs all inner commands sequentially.
    """

    type: Literal["group"] = "group"
    commands: list[SerializeAsAny[Command]] = Field(default_factory=list)

    def execute(self) -> int:
        for cmd in self.commands:
            if cmd.label:
                print(f"    {cmd.label}")
            returncode = cmd.execute()
            if cmd.check and returncode != 0:
                return returncode
        return 0


# ---------------------------------------------------------------------------
# JOB / WORKFLOW
# ---------------------------------------------------------------------------


class Job(BaseModel):
    """A single job in the release workflow DAG."""

    model_config = ConfigDict(frozen=True)

    name: str
    needs: list[str] = Field(default_factory=list)
    commands: list[SerializeAsAny[Command]] = Field(default_factory=list)
    pre_hook: str = ""
    post_hook: str = ""

    @field_validator("commands", mode="before")
    @classmethod
    def _deserialize_commands(cls, v: Any) -> Any:
        """When deserializing from JSON, parse dicts through the discriminated command union."""
        from pydantic import TypeAdapter

        from .commands import AnyCommand

        return tuple(TypeAdapter(list[AnyCommand]).validate_python(list(v)))


# ---------------------------------------------------------------------------
# WORKFLOW
# ---------------------------------------------------------------------------


class Workflow(BaseModel):
    """The release workflow. A DAG of jobs with a pre-computed execution order."""

    model_config = ConfigDict(frozen=True)

    jobs: dict[str, Job] = Field(default_factory=dict)
    job_order: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# PLAN
# ---------------------------------------------------------------------------


class Plan(BaseModel):
    """The final pipeline output. Holds everything needed to execute a release."""

    model_config = ConfigDict(frozen=True, extra="allow")

    workspace: Workspace
    changes: dict[str, Change] = Field(default_factory=dict)
    releases: dict[str, Release] = Field(default_factory=dict)
    workflow: Workflow = Workflow()
    target: Literal["ci", "local"] = "local"
    build_matrix: list[list[str]] = Field(default_factory=lambda: [["ubuntu-latest"]])
    python_version: str = "3.12"
    publish_environment: str = ""
    skip: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# MERGE_RESULT
# ---------------------------------------------------------------------------


class MergeResult(BaseModel):
    """Result of a three-way merge operation."""

    model_config = ConfigDict(frozen=True)

    path: str
    has_conflicts: bool = False
    is_new: bool = False
