"""All frozen entity types for the uv_release pipeline."""

from __future__ import annotations

from abc import ABC
from enum import Enum
from typing import Any, Literal, Protocol

from packaging.version import Version as PkgVersion
from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, field_validator


# ---------------------------------------------------------------------------
# Unset sentinel (shared by planner and executor)
# ---------------------------------------------------------------------------


class Unset(Enum):
    """Sentinel for unset optional parameters."""

    TOKEN = "TOKEN"


UNSET = Unset.TOKEN


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
    dependencies: list[str] = Field(default_factory=list)

    @staticmethod
    def format_dist_name(name: str) -> str:
        """Wheel distribution name (PEP 625) from a raw package name."""
        from packaging.utils import canonicalize_name

        return canonicalize_name(name).replace("-", "_")

    @property
    def dist_name(self) -> str:
        """Wheel distribution name (PEP 625). Used for glob patterns."""
        return Package.format_dist_name(self.name)


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


class Hooks(ABC):
    """User-provided release hooks. Subclass to customize lifecycle behavior."""

    DEFAULT_FILE = "uvr_hooks.py"
    DEFAULT_CLASS = "Hooks"

    def pre_plan(self, workspace: Any, intent: Any) -> Any:
        return intent

    def post_plan(self, workspace: Any, intent: Any, plan: Any) -> Any:
        return plan

    def pre_build(self) -> None:
        pass

    def post_build(self) -> None:
        pass

    def pre_release(self) -> None:
        pass

    def post_release(self) -> None:
        pass

    def pre_publish(self) -> None:
        pass

    def post_publish(self) -> None:
        pass

    def pre_bump(self) -> None:
        pass

    def post_bump(self) -> None:
        pass


# ---------------------------------------------------------------------------
# PLAN PARAMS
# ---------------------------------------------------------------------------


class PlanParams(BaseModel):
    """CLI flags passed through the pipeline. Not a State."""

    model_config = ConfigDict(frozen=True)

    all_packages: bool = False
    packages: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# PYPROJECT STRUCTURE (shared by states/ and commands/)
# ---------------------------------------------------------------------------


class ProjectTable(BaseModel):
    """The [project] table from a package's pyproject.toml."""

    model_config = ConfigDict(frozen=True, extra="allow")

    name: str = ""
    version: str = ""
    dependencies: list[str] = Field(default_factory=list)


class BuildSystemTable(BaseModel):
    """The [build-system] table from a package's pyproject.toml."""

    model_config = ConfigDict(frozen=True, extra="allow")

    requires: list[str] = Field(default_factory=list)


class PackagePyProject(BaseModel):
    """A package-level pyproject.toml."""

    model_config = ConfigDict(frozen=True, extra="allow")

    project: ProjectTable = Field(default_factory=ProjectTable)
    build_system: BuildSystemTable = Field(
        default_factory=BuildSystemTable, alias="build-system"
    )


class UvWorkspaceTable(BaseModel):
    """The [tool.uv.workspace] table."""

    model_config = ConfigDict(frozen=True, extra="allow")

    members: list[str] = Field(default_factory=list)


class UvTable(BaseModel):
    """The [tool.uv] table."""

    model_config = ConfigDict(frozen=True, extra="allow")

    workspace: UvWorkspaceTable = Field(default_factory=UvWorkspaceTable)


class UvrConfigTable(BaseModel):
    """The [tool.uvr.config] table."""

    model_config = ConfigDict(frozen=True, extra="allow")

    latest: str = ""
    python_version: str = "3.12"
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class UvrPublishTable(BaseModel):
    """The [tool.uvr.publish] table."""

    model_config = ConfigDict(frozen=True, extra="allow")

    index: str = ""
    environment: str = ""
    trusted_publishing: str = Field(default="automatic", alias="trusted-publishing")
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class UvrHooksTable(BaseModel):
    """The [tool.uvr.hooks] table."""

    model_config = ConfigDict(frozen=True, extra="allow")

    file: str = ""


class UvrTable(BaseModel):
    """The [tool.uvr] table."""

    model_config = ConfigDict(frozen=True, extra="allow")

    config: UvrConfigTable = Field(default_factory=UvrConfigTable)
    runners: dict[str, list[list[str]]] = Field(default_factory=dict)
    publish: UvrPublishTable = Field(default_factory=UvrPublishTable)
    hooks: UvrHooksTable = Field(default_factory=UvrHooksTable)


class ToolTable(BaseModel):
    """The [tool] table from the root pyproject.toml."""

    model_config = ConfigDict(frozen=True, extra="allow")

    uv: UvTable = Field(default_factory=UvTable)
    uvr: UvrTable = Field(default_factory=UvrTable)


class RootPyProject(BaseModel):
    """The root pyproject.toml structure."""

    model_config = ConfigDict(frozen=True, extra="allow")

    tool: ToolTable = Field(default_factory=ToolTable)


# ---------------------------------------------------------------------------
# TOML DOCUMENT WRAPPERS (typed access + comment preservation)
# ---------------------------------------------------------------------------


class PackagePyProjectDoc:
    """Typed wrapper around a tomlkit document for a package pyproject.toml.

    Reads and writes go through the same tomlkit doc, so comments survive.
    Used by commands for mutation. States use the Pydantic models above for parsing.
    """

    def __init__(self, doc: Any) -> None:
        self._doc = doc

    @classmethod
    def read(cls, path: str) -> PackagePyProjectDoc:
        """Read a pyproject.toml from disk."""
        import tomlkit
        from pathlib import Path

        return cls(tomlkit.loads(Path(path).read_text()))

    def write(self, path: str) -> None:
        """Write the document back to disk, preserving comments."""
        import tomlkit
        from pathlib import Path

        Path(path).write_text(tomlkit.dumps(self._doc))

    @property
    def name(self) -> str:
        return str(self._doc["project"]["name"])

    @property
    def version(self) -> str:
        return str(self._doc["project"]["version"])

    @version.setter
    def version(self, value: str) -> None:
        self._doc["project"]["version"] = value

    @property
    def dependencies(self) -> list[Any]:
        return self._doc.get("project", {}).get("dependencies", [])

    @property
    def build_requires(self) -> list[Any]:
        return self._doc.get("build-system", {}).get("requires", [])


class WorkspacePyProjectDoc:
    """Typed wrapper around a tomlkit document for the root pyproject.toml.

    Provides typed access to [tool.uvr.*] sections while preserving comments.
    """

    def __init__(self, doc: Any) -> None:
        self._doc = doc

    @classmethod
    def read(cls, path: str = "pyproject.toml") -> WorkspacePyProjectDoc:
        """Read the root pyproject.toml from disk."""
        import tomlkit
        from pathlib import Path

        return cls(tomlkit.loads(Path(path).read_text()))

    def write(self, path: str = "pyproject.toml") -> None:
        """Write the document back to disk, preserving comments."""
        import tomlkit
        from pathlib import Path

        Path(path).write_text(tomlkit.dumps(self._doc))

    def set_config(self, key: str, value: str) -> None:
        """Set a key in [tool.uvr.config]."""
        tool = self._doc.setdefault("tool", {})
        uvr = tool.setdefault("uvr", {})
        config = uvr.setdefault("config", {})
        config[key] = value

    @property
    def workspace_members(self) -> list[str]:
        return (
            self._doc.get("tool", {})
            .get("uv", {})
            .get("workspace", {})
            .get("members", [])
        )


# ---------------------------------------------------------------------------
# WORKSPACE
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CHANGE
# ---------------------------------------------------------------------------


class Change(BaseModel):
    """A package that changed since its baseline. Produced by Changes.parse()."""

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
    """A changed package planned for release. Constructed by intent plan() methods."""

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
    """A named group of commands with optional lifecycle hooks."""

    model_config = ConfigDict(frozen=True)

    name: str
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
# PLAN_METADATA
# ---------------------------------------------------------------------------


class PlanMetadata(BaseModel):
    """Transient context from plan computation. Not serialized."""

    model_config = ConfigDict(frozen=True)

    workspace: Any | None = None
    uvr_state: Any | None = None
    workflow_state: Any | None = None


# ---------------------------------------------------------------------------
# PLAN
# ---------------------------------------------------------------------------


class Plan(BaseModel):
    """What to execute. Nothing more."""

    model_config = ConfigDict(frozen=True)

    # CI (read by GitHub Actions YAML via fromJSON)
    build_matrix: list[list[str]] = Field(default_factory=lambda: [["ubuntu-latest"]])
    python_version: str = "3.12"
    publish_environment: str = ""
    skip: list[str] = Field(default_factory=list)
    reuse_run: str = ""
    reuse_release: bool = False

    # Execution
    jobs: list[SerializeAsAny[Job]] = Field(default_factory=list)

    # Results (populated by read-only intents)
    changes: tuple[Change, ...] = ()
    validation_errors: tuple[str, ...] = ()
    validation_warnings: tuple[str, ...] = ()

    # Transient (excluded from serialization, populated by compute_plan)
    metadata: PlanMetadata = Field(default_factory=PlanMetadata, exclude=True)


# ---------------------------------------------------------------------------
# MERGE_RESULT
# ---------------------------------------------------------------------------


class MergeResult(BaseModel):
    """Result of a three-way merge operation."""

    model_config = ConfigDict(frozen=True)

    path: str
    has_conflicts: bool = False
    is_new: bool = False


# ---------------------------------------------------------------------------
# INTENT PROTOCOL
# ---------------------------------------------------------------------------


class Intent(Protocol):
    """Protocol for all intent types.

    Intents declare state dependencies as keyword-only parameters
    on guard() and plan(). The planner inspects type hints, resolves
    only what each intent declares, and passes them as kwargs.
    """

    def guard(self, **state: object) -> None: ...
    def plan(self, **state: object) -> Plan: ...


class UserRecoverableError(ValueError):
    """Error that the user can recover from by executing commands.

    The fix CommandGroup is presented to the user for confirmation.
    If they accept, the caller executes the commands and retries.
    """

    def __init__(self, message: str, fix: CommandGroup) -> None:
        super().__init__(message)
        self.fix = fix
