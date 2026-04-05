"""CLI entry point for uv-release-monorepo."""

from __future__ import annotations

from ..shared.models import PlanConfig, ReleasePlan  # noqa: F401 (re-exported)
from ..shared.planner import ReleasePlanner, build_plan
from ..shared.executor import ReleaseExecutor
from ..shared.utils.cli import __version__
from ..shared.utils.yaml import MISSING, yaml_delete, yaml_get, yaml_set
from ._cli import cli
from .bump import cmd_bump
from .download import cmd_download
from .install import cmd_install
from .release import cmd_release
from .workflow import (
    cmd_init,
    cmd_publish_config,
    cmd_runners,
    cmd_upgrade,
    cmd_validate,
)

__all__ = [
    "MISSING",
    "__version__",
    "yaml_delete",
    "yaml_get",
    "yaml_set",
    "cmd_bump",
    "PlanConfig",
    "ReleaseExecutor",
    "ReleasePlanner",
    "build_plan",
    "cli",
    "cmd_init",
    "cmd_install",
    "cmd_publish_config",
    "cmd_release",
    "cmd_runners",
    "cmd_upgrade",
    "cmd_validate",
    "cmd_download",
]
