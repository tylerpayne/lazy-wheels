"""The ``uvr workflow runners`` command."""

from __future__ import annotations

import argparse

from .._args import CommandArgs, compute_plan_or_exit
from ...intents.configure_runners import ConfigureRunnersIntent
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

    plan = compute_plan_or_exit(intent)

    if not plan.jobs:
        uvr_state = plan.metadata.uvr_state
        workspace = plan.metadata.workspace
        assert uvr_state is not None
        assert workspace is not None
        if parsed.package:
            runners = uvr_state.runners.get(parsed.package, _DEFAULT_RUNNERS)
            for r in runners:
                print(f"  [{', '.join(r)}]")
        else:
            _print_all_runners(workspace, uvr_state)
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


def _print_all_runners(workspace: object, uvr_state: object) -> None:
    """Print effective runners for all packages."""
    from ...states.uvr_state import UvrState
    from ...states.workspace import Workspace

    assert isinstance(workspace, Workspace)
    assert isinstance(uvr_state, UvrState)
    if not workspace.packages:
        print("No packages found.")
        return
    nw = max(len(n) for n in workspace.packages)
    for name in sorted(workspace.packages):
        runners = uvr_state.runners.get(name, _DEFAULT_RUNNERS)
        labels = ", ".join(f"[{', '.join(r)}]" for r in runners)
        print(f"  {name.ljust(nw)}  {labels}")
