"""The ``uvr jobs publish`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from ...shared.executor import ReleaseExecutor
from ...shared.hooks import load_hook
from ...shared.models import ReleasePlan
from ...shared.utils.cli import resolve_plan_json
from .._args import CommandArgs


class JobPublishArgs(CommandArgs):
    """Typed arguments for ``uvr jobs publish``."""

    plan: str | None = None


def cmd_publish_to_index(args: argparse.Namespace) -> None:
    """Publish wheels to package indexes."""
    parsed = JobPublishArgs.from_namespace(args)
    plan_obj = ReleasePlan.model_validate_json(resolve_plan_json(parsed.plan))
    hook = load_hook(Path.cwd())
    ReleaseExecutor(plan_obj, hook).publish_to_index()
