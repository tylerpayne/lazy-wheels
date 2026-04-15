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


def print_status_table(plan: Plan, *, show_release_version: bool = True) -> None:
    """Print the status table showing changed and unchanged packages."""
    all_names = sorted({*plan.releases.keys(), *plan.workspace.packages.keys()})
    if not all_names:
        return

    rows: list[tuple[str, ...]] = []
    for name in all_names:
        if name in plan.releases:
            release = plan.releases[name]
            change = plan.changes.get(name)
            reason = change.reason if change else "changed"
            diff_from = "-"
            if change and change.baseline:
                diff_from = change.baseline.raw
            changes = change.diff_stats or "-" if change else "-"
            commits = "-"
            if change and change.baseline and change.commit_log:
                commits = str(change.commit_log.count("\n") + 1)
            base = (
                reason,
                name,
                release.package.version.raw,
            )
            if show_release_version:
                base = (*base, release.release_version.raw)
            rows.append((*base, diff_from, changes, commits))
        else:
            pkg = plan.workspace.packages[name]
            base = ("unchanged", name, pkg.version.raw)
            if show_release_version:
                base = (*base, "-")
            rows.append((*base, "-", "-", "-"))

    headers = ("STATUS", "PACKAGE", "VERSION")
    if show_release_version:
        headers = (*headers, "WILL RELEASE")
    headers = (*headers, "DIFF FROM", "CHANGES", "COMMITS")
    for line in format_table(headers, rows):
        print(line)


def print_plan_summary(plan: Plan) -> None:
    """Print the full release plan with pipeline and job details."""
    print_status_table(plan)

    if not plan.releases:
        return

    print()
    print("Pipeline")
    print("--------")
    for job_name in plan.workflow.job_order:
        job = plan.workflow.jobs.get(job_name)
        if job is None:
            continue
        has_cmds = len(job.commands) > 0
        status = "run" if has_cmds else "skip"
        print(f"  {status.ljust(6)}  {job_name}")

    # Release notes
    notes = {n: r for n, r in plan.releases.items() if r.release_notes.strip()}
    if notes:
        print()
        print("Release Notes")
        print("-------------")
        for name, release in sorted(notes.items()):
            print(f"  {name}")
            for line in release.release_notes.strip().splitlines():
                print(f"    {line}")
            print()


def print_bump_summary(results: list[tuple[str, str, str]]) -> None:
    """Print a before/after version table for bump results."""
    if not results:
        return
    nw = max(len(name) for name, _, _ in results)
    ow = max(len(old) for _, old, _ in results)
    for name, old, new in results:
        print(f"  {name.ljust(nw)}  {old.ljust(ow)}  ->  {new}")
