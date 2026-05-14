"""Pydantic models for pyproject.toml structures."""

from __future__ import annotations

from pydantic import Field

from .base import Frozen

# extra="allow" so unknown pyproject.toml fields don't fail validation.


# --- Package pyproject.toml ---


class ProjectTable(Frozen, extra="allow"):
    """The [project] table from a package's pyproject.toml."""

    name: str = ""
    version: str = ""
    dependencies: list[str] = Field(default_factory=list)


class BuildSystemTable(Frozen, extra="allow"):
    """The [build-system] table from a package's pyproject.toml."""

    requires: list[str] = Field(default_factory=list)


class PackagePyProject(Frozen, extra="allow"):
    """A package-level pyproject.toml."""

    project: ProjectTable = Field(default_factory=ProjectTable)
    build_system: BuildSystemTable = Field(
        default_factory=BuildSystemTable, alias="build-system"
    )


# --- Root pyproject.toml ---


class UvWorkspaceTable(Frozen, extra="allow"):
    """The [tool.uv.workspace] table."""

    members: list[str] = Field(default_factory=list)


class UvTable(Frozen, extra="allow"):
    """The [tool.uv] table."""

    workspace: UvWorkspaceTable = Field(default_factory=UvWorkspaceTable)


class UvrConfigTable(Frozen, extra="allow"):
    """The [tool.uvr.config] table."""

    latest: str = ""
    python_version: str = "3.12"
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    # uv-release version whose workflow/skill templates were last accepted.
    # Used by `uvr workflow install --upgrade` and `uvr skill install --upgrade`
    # to fetch the correct base for three-way merge via uvx.
    workflow_version: str = Field(default="", alias="workflow-version")
    skill_version: str = Field(default="", alias="skill-version")


class UvrPublishTable(Frozen, extra="allow"):
    """The [tool.uvr.publish] table."""

    index: str = ""
    environment: str = ""
    # Alias maps TOML kebab-case key to Python snake_case.
    trusted_publishing: str = Field(default="automatic", alias="trusted-publishing")
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class UvrHooksTable(Frozen, extra="allow"):
    """The [tool.uvr.hooks] table."""

    file: str = ""


class UvrTable(Frozen, extra="allow"):
    """The [tool.uvr] table."""

    config: UvrConfigTable = Field(default_factory=UvrConfigTable)
    # { pkg: [[label, ...], ...] } -- each inner list is one CI matrix row.
    runners: dict[str, list[list[str]]] = Field(default_factory=dict)
    publish: UvrPublishTable = Field(default_factory=UvrPublishTable)
    hooks: UvrHooksTable = Field(default_factory=UvrHooksTable)


class ToolTable(Frozen, extra="allow"):
    """The [tool] table from the root pyproject.toml."""

    uv: UvTable = Field(default_factory=UvTable)
    uvr: UvrTable = Field(default_factory=UvrTable)


class RootPyProject(Frozen, extra="allow"):
    """The root pyproject.toml structure.

    The root may itself be a package (single-package layout: it carries
    [project] and [build-system] tables and no [tool.uv.workspace]) or
    only a workspace root (multi-package layout: it carries
    [tool.uv.workspace] and no [project]). A root that is both is
    rejected during workspace discovery.
    """

    project: ProjectTable = Field(default_factory=ProjectTable)
    build_system: BuildSystemTable = Field(
        default_factory=BuildSystemTable, alias="build-system"
    )
    tool: ToolTable = Field(default_factory=ToolTable)
