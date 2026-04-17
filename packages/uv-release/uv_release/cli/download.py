"""The ``uvr download`` command."""

from __future__ import annotations

import argparse
import sys

from ._args import CommandArgs
from ..intents.download import DownloadIntent
from ..planner import compute_plan
from ..execute import execute_plan


class DownloadArgs(CommandArgs):
    """Typed arguments for ``uvr download``."""

    output: str = "dist"
    run_id: str | None = None
    package: str | None = None
    release_tag: str | None = None
    repo: str | None = None
    all_platforms: bool = False


def cmd_download(args: argparse.Namespace) -> None:
    """Download wheels from a GitHub release or CI run."""
    parsed = DownloadArgs.from_namespace(args)

    intent = DownloadIntent(
        package=parsed.package or "",
        release_tag=parsed.release_tag or "",
        run_id=parsed.run_id or "",
        repo=parsed.repo or "",
        output=parsed.output,
    )

    try:
        plan = compute_plan(intent)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    execute_plan(plan, hooks=None)
