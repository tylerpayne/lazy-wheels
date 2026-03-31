"""The ``uvr status`` command."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from ..shared.utils.cli import __version__
from ..shared.utils.cli import diff_stat, read_matrix
from ..shared.models import PlanConfig
from ..shared.planner import ReleasePlanner
from ..shared.context import build_context
from ..shared.utils.versions import detect_release_type


def cmd_status(args: argparse.Namespace) -> None:
    """Show workspace package status from the release planner."""
    # Suppress planner's verbose discovery output
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        ctx = build_context()
        release_type = detect_release_type(ctx.packages)
        config = PlanConfig(
            rebuild_all=getattr(args, "rebuild_all", False),
            matrix=read_matrix(Path.cwd()),
            uvr_version=__version__,
            ci_publish=True,
            release_type=release_type,
            dry_run=True,
        )
        plan = ReleasePlanner(config, ctx).plan()
    finally:
        sys.stdout = old_stdout

    # Collect rows: (status, name, version, previous, changes, commits)
    rows: list[tuple[str, str, str, str, str, str]] = []
    for name, pkg in sorted(plan.changed.items()):
        baseline = f"{name}/v{pkg.current_version}-base"
        changes, commits = diff_stat(baseline, pkg.path)
        rows.append(
            (
                "changed",
                name,
                pkg.current_version,
                pkg.last_release_tag.split("/v", 1)[1] if pkg.last_release_tag else "-",
                changes,
                commits,
            )
        )
    for name, pkg in sorted(plan.unchanged.items()):
        rows.append(
            (
                "unchanged",
                name,
                pkg.version,
                "-",
                "-",
                "-",
            )
        )

    if not rows:
        print("No packages found.")
        return

    headers = ("STATUS", "PACKAGE", "VERSION", "PREVIOUS", "CHANGES", "COMMITS")
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def _row(cols: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cols, widths))

    print()
    print("Packages")
    print("--------")
    print(f"  {_row(headers)}")
    for row in rows:
        print(f"  {_row(row)}")
    print()
