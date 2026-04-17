"""Display and formatting for CLI output."""

from __future__ import annotations

from ..types import Plan


def format_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    """Format rows into aligned columns. Returns lines without trailing newlines."""
    if not rows:
        return []
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines: list[str] = []
    lines.append("  " + "  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    for row in rows:
        lines.append("  " + "  ".join(cell.ljust(w) for cell, w in zip(row, widths)))
    return lines


def print_plan_summary(plan: Plan) -> None:
    """Print the release plan pipeline summary."""
    if not plan.jobs:
        return

    print("Pipeline")
    print("--------")
    for job in plan.jobs:
        has_cmds = len(job.commands) > 0
        status = "run" if has_cmds else "skip"
        print(f"  {status.ljust(6)}  {job.name}")


def print_bump_summary(results: list[tuple[str, str, str]]) -> None:
    """Print a before/after version table for bump results."""
    if not results:
        return
    nw = max(len(name) for name, _, _ in results)
    ow = max(len(old) for _, old, _ in results)
    for name, old, new in results:
        print(f"  {name.ljust(nw)}  {old.ljust(ow)}  ->  {new}")
