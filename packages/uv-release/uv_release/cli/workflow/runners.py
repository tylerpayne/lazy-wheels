"""The ``uvr workflow runners`` command."""

from __future__ import annotations

import argparse
import sys

from .._args import CommandArgs
from ...intents.configure_runners import ConfigureRunnersIntent
from ...planner import compute_plan
from ...execute import execute_plan

_DEFAULT_RUNNERS: list[list[str]] = [["ubuntu-latest"]]


class RunnersArgs(CommandArgs):
    """Typed arguments for ``uvr workflow runners``."""

    package: str | None = None
    add_runners: list[str] | None = None
    remove_runners: list[str] | None = None
    clear: bool = False


def cmd_runners(args: argparse.Namespace) -> None:
    """Manage per-package build runners in [tool.uvr.runners]."""
    parsed = RunnersArgs.from_namespace(args)

    intent = ConfigureRunnersIntent(
        package=parsed.package or "",
        add=parsed.add_runners or [],
        remove=parsed.remove_runners or [],
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
        if parsed.package:
            runners = workspace.runners.get(parsed.package, _DEFAULT_RUNNERS)
            for r in runners:
                print(f"  [{', '.join(r)}]")
        else:
            _print_all_runners(workspace)
        return

    execute_plan(plan, hooks=None)

    if parsed.clear:
        print(
            f"Cleared runners for '{parsed.package}'."
            if parsed.package
            else "Cleared all runners."
        )
    elif parsed.add_runners:
        added = ", ".join(f"[{r}]" for r in parsed.add_runners)
        print(f"Added {added} to '{parsed.package}' runners.")
    elif parsed.remove_runners:
        removed = ", ".join(f"[{r}]" for r in parsed.remove_runners)
        print(f"Removed {removed} from '{parsed.package}' runners.")


def _print_all_runners(workspace: object) -> None:
    """Print effective runners for all packages."""
    from ...types import Workspace

    assert isinstance(workspace, Workspace)
    if not workspace.packages:
        print("No packages found.")
        return
    nw = max(len(n) for n in workspace.packages)
    for name in sorted(workspace.packages):
        runners = workspace.runners.get(name, _DEFAULT_RUNNERS)
        labels = ", ".join(f"[{', '.join(r)}]" for r in runners)
        print(f"  {name.ljust(nw)}  {labels}")
