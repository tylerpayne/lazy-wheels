"""The ``uvr clean`` command."""

from __future__ import annotations

import argparse
import sys

from ._args import CommandArgs
from ..intents.clean import CleanIntent
from ..planner import compute_plan
from ..execute import execute_plan


class CleanArgs(CommandArgs):
    """Typed arguments for ``uvr clean``."""


def cmd_clean(args: argparse.Namespace) -> None:
    """Remove uvr caches and ephemeral files."""
    _parsed = CleanArgs.from_namespace(args)

    intent = CleanIntent()
    try:
        plan = compute_plan(intent)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not plan.jobs or not plan.jobs[0].commands:
        print("Nothing to clean.")
        return

    execute_plan(plan, hooks=None)
    print("Cleaned.")
