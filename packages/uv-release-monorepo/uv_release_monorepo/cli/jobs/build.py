"""The ``uvr jobs build`` command."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ...shared.executor import ReleaseExecutor
from ...shared.hooks import load_hook
from ...shared.models import ReleasePlan
from ...shared.utils.cli import fatal, resolve_plan_json
from .._args import CommandArgs


class JobBuildArgs(CommandArgs):
    """Typed arguments for ``uvr jobs build``."""

    plan: str | None = None
    runner: str | None = None


def _resolve_runner(raw: str | None) -> str:
    """Resolve runner JSON from --runner arg or UVR_RUNNER env var."""
    value = raw or os.environ.get("UVR_RUNNER")
    if not value:
        fatal("No runner provided. Pass --runner JSON or set UVR_RUNNER.")
    return value


def cmd_build(args: argparse.Namespace) -> None:
    """Build packages for a runner."""
    parsed = JobBuildArgs.from_namespace(args)
    plan_obj = ReleasePlan.model_validate_json(resolve_plan_json(parsed.plan))
    hook = load_hook(Path.cwd())
    ReleaseExecutor(plan_obj, hook).build(runner=_resolve_runner(parsed.runner))
