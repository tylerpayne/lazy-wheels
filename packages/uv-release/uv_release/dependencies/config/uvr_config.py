"""UvrConfig: workspace-level release configuration."""

from __future__ import annotations

from pathlib import Path

import tomlkit
from diny import singleton, provider

from ...types.base import Frozen
from ...types.pyproject import RootPyProject
from ..shared.workspace_packages import WorkspacePackages


@singleton
class UvrConfig(Frozen):
    """From [tool.uvr.config]."""

    latest_package: str = ""
    python_version: str = "3.12"
    include: frozenset[str] = frozenset()
    exclude: frozenset[str] = frozenset()
    # uv-release version whose templates were last accepted (empty if never).
    workflow_version: str = ""
    skill_version: str = ""


@provider(UvrConfig)
def provide_uvr_config(workspace_packages: WorkspacePackages) -> UvrConfig:
    doc = RootPyProject.model_validate(
        tomlkit.loads(Path("pyproject.toml").read_text())
    )
    config = doc.tool.uvr.config

    # When the workspace contains exactly one package (the common case for
    # the single-package layout where the root pyproject IS the package)
    # default `latest` to that package. The "latest" marker only matters
    # when there is something to pick between, so omitting it from the
    # config in a one-package workspace should not be required.
    latest_package = config.latest
    if not latest_package and len(workspace_packages.items) == 1:
        latest_package = next(iter(workspace_packages.items))

    return UvrConfig(
        latest_package=latest_package,
        python_version=config.python_version,
        include=frozenset(config.include),
        exclude=frozenset(config.exclude),
        workflow_version=config.workflow_version,
        skill_version=config.skill_version,
    )
