"""CLI entry point for uv-release-monorepo."""

from __future__ import annotations

from ..shared.models import PlanConfig, ReleasePlan  # noqa: F401 (re-exported)
from ..shared.planner import ReleasePlanner, build_plan
from ..shared.executor import ReleaseExecutor
from ..shared.utils.cli import __version__
from ._yaml import _MISSING, _yaml_delete, _yaml_get, _yaml_set
from ._cli import cli
from .init import cmd_init, cmd_upgrade, cmd_validate
from .install import cmd_install
from .bump import cmd_bump
from .release import cmd_release
from .runners import cmd_runners
from .wheels import cmd_wheels

__all__ = [
    "_MISSING",
    "__version__",
    "_yaml_delete",
    "_yaml_get",
    "_yaml_set",
    "cmd_bump",
    "PlanConfig",
    "ReleaseExecutor",
    "ReleasePlanner",
    "build_plan",
    "cli",
    "cmd_init",
    "cmd_install",
    "cmd_release",
    "cmd_runners",
    "cmd_upgrade",
    "cmd_validate",
    "cmd_wheels",
]
