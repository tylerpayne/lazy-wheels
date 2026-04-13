"""The ``uvr status`` command."""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
from pathlib import Path

from ._args import CommandArgs
from ..shared.utils.cli import __version__, diff_stat, read_matrix
from ..shared.models import PlanConfig
from ..shared.planner import ReleasePlanner
from ..shared.context import build_context
from ..shared.resolution import ReleaseInvalidError, resolve_release


class StatusArgs(CommandArgs):
    """Typed arguments for ``uvr status``."""

    rebuild_all: bool = False
    rebuild: list[str] | None = None


def cmd_status(args: argparse.Namespace) -> None:
    """Show workspace package status from the release planner."""
    parsed = StatusArgs.from_namespace(args)

    # Warn on dirty working tree
    result = subprocess.run(
        ["git", "status", "--short"], capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        print("WARNING: Working tree is not clean.", file=sys.stderr)
        print(result.stdout.rstrip(), file=sys.stderr)

    # Suppress planner's verbose discovery output
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        ctx = build_context()
        config = PlanConfig(
            rebuild_all=parsed.rebuild_all,
            matrix=read_matrix(Path.cwd()),
            rebuild=parsed.rebuild or [],
            uvr_version=__version__,
            ci_publish=True,
            dry_run=True,
        )
        plan = ReleasePlanner(config, ctx).plan()
    finally:
        sys.stdout = old_stdout

    # Collect rows: (status, name, version, previous, diff_from, changes, commits)
    rows: list[tuple[str, ...]] = []
    for name, pkg in sorted(plan.changed.items()):
        baseline = pkg.baseline_tag
        changes, commits, diff_tag = diff_stat(
            baseline, pkg.path, fallback_tag=pkg.last_release_tag
        )
        rows.append(
            (
                "changed",
                name,
                pkg.current_version,
                pkg.last_release_tag.split("/v", 1)[1] if pkg.last_release_tag else "-",
                diff_tag,
                changes,
                commits,
            )
        )
    for name, pkg in sorted(plan.unchanged.items()):
        try:
            r = resolve_release(pkg.version, name, ctx.repo)
        except ReleaseInvalidError:
            r = None
        baseline = r.baseline_tag if r else None
        _, _, diff_tag = diff_stat(baseline, pkg.path)
        from ..shared.utils.versions import find_release_tags_below, strip_dev

        prev_tags = find_release_tags_below(
            strip_dev(pkg.version), name, ctx.repo, limit=1
        )
        prev = prev_tags[0] if prev_tags else None
        rows.append(
            (
                "unchanged",
                name,
                pkg.version,
                prev or "-",
                diff_tag,
                "-",
                "-",
            )
        )

    if not rows:
        print("No packages found.")
        return

    headers = (
        "STATUS",
        "PACKAGE",
        "VERSION",
        "PREVIOUS",
        "DIFF FROM",
        "CHANGES",
        "COMMITS",
    )
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def _row(cols: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cols, widths))

    print()
    print("Packages")
    print("--------")
    print(f"  {_row(headers)}")
    for row in rows:
        print(f"  {_row(row)}")

    # Collect warnings (version/tag conflicts detected by resolve_release)
    all_warnings: list[str] = []
    for name, pkg in ctx.packages.items():
        try:
            resolve_release(pkg.version, name, ctx.repo)
        except ReleaseInvalidError as e:
            msg = str(e)
            if e.conflict.hint:
                msg += f"\n    Fix: {e.conflict.hint}"
            all_warnings.append(msg)

    if all_warnings:
        print()
        print("Warnings")
        print("--------")
        for warning in all_warnings:
            print(f"  {warning}")

    print()
