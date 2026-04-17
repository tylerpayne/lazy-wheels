"""The ``uvr workflow config`` command."""

from __future__ import annotations

import argparse
import sys

from .._args import CommandArgs
from ...intents.configure import ConfigureIntent
from ...planner import compute_plan
from ...execute import execute_plan


class ConfigArgs(CommandArgs):
    """Typed arguments for ``uvr workflow config``."""

    editor: str | None = None
    latest: str | None = None
    include_packages: list[str] | None = None
    exclude_packages: list[str] | None = None
    remove_packages: list[str] | None = None
    clear: bool = False


def cmd_config(args: argparse.Namespace) -> None:
    """Manage workspace config in [tool.uvr.config]."""
    parsed = ConfigArgs.from_namespace(args)

    updates: dict[str, str] = {}
    if parsed.editor is not None:
        updates["editor"] = parsed.editor
    if parsed.latest is not None:
        updates["latest"] = parsed.latest

    intent = ConfigureIntent(
        updates=updates,
        add_include=parsed.include_packages or [],
        add_exclude=parsed.exclude_packages or [],
        remove_packages=parsed.remove_packages or [],
        clear=parsed.clear,
    )

    try:
        plan = compute_plan(intent)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not plan.jobs:
        workspace = plan.metadata.workspace
        assert workspace is not None
        _print_config(workspace)
        return

    execute_plan(plan, hooks=None)

    if parsed.clear:
        print("Cleared workspace config.")
    else:
        print("Updated workspace config.")


def _print_config(workspace: object) -> None:
    """Print the current workspace config."""
    from ...types import Workspace

    assert isinstance(workspace, Workspace)
    config = workspace.config

    include = sorted(config.include)
    exclude = sorted(config.exclude)
    latest = config.latest_package

    if not any([include, exclude, latest]):
        print("No workspace config set.")
        return

    if include:
        print(f"  include: {', '.join(include)}")
    if exclude:
        print(f"  exclude: {', '.join(exclude)}")
    if latest:
        print(f"  latest:  {latest}")
