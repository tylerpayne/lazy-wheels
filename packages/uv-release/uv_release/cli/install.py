"""The ``uvr install`` command."""

from __future__ import annotations

import argparse

from ._args import CommandArgs, compute_plan_or_exit
from ..intents.install import InstallIntent
from ..execute import execute_plan


class InstallArgs(CommandArgs):
    """Typed arguments for ``uvr install``."""

    packages: list[str] | None = None
    run_id: str | None = None
    repo: str | None = None
    dist: str | None = None


def cmd_install(args: argparse.Namespace) -> None:
    """Install packages from GitHub releases, CI artifacts, or local wheels."""
    parsed = InstallArgs.from_namespace(args)

    intent = InstallIntent(
        packages=parsed.packages or [],
        dist=parsed.dist or "",
        repo=parsed.repo or "",
    )

    plan = compute_plan_or_exit(intent)
    execute_plan(plan, hooks=None)
