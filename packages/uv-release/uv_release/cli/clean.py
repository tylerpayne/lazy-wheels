"""The ``uvr clean`` command."""

from __future__ import annotations

import argparse

from ._args import CommandArgs, compute_plan_or_exit
from ..intents.clean import CleanIntent
from ..execute import execute_plan


class CleanArgs(CommandArgs):
    """Typed arguments for ``uvr clean``."""


def cmd_clean(args: argparse.Namespace) -> None:
    """Remove uvr caches and ephemeral files."""
    _parsed = CleanArgs.from_namespace(args)

    intent = CleanIntent()
    plan = compute_plan_or_exit(intent)

    if not plan.jobs or not plan.jobs[0].commands:
        print("Nothing to clean.")
        return

    execute_plan(plan, hooks=None)
    print("Cleaned.")
