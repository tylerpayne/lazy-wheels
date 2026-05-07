"""uvr status: show workspace package status."""

from __future__ import annotations

from diny import inject

from .. import ui
from ..dependencies.config.uvr_config import UvrConfig
from ..dependencies.shared.baseline_tags import BaselineTags
from ..dependencies.shared.changed_packages import ChangedPackages
from ..dependencies.shared.workspace_packages import WorkspacePackages


# Map ChangedPackages reasons to badge kinds. Anything not present here
# falls through to the literal reason string with a dim style.
_REASON_TO_BADGE = {
    "unchanged": "unchanged",
    "changed": "changed",
}


@inject
def cmd_status(
    workspace_packages: WorkspacePackages,
    changed_packages: ChangedPackages,
    baseline_tags: BaselineTags,
    uvr_config: UvrConfig,
) -> None:
    # Apply [tool.uvr.config].include / exclude so status matches the
    # workspace view that build/release/version operate on.
    items = dict(workspace_packages.items)
    if uvr_config.include:
        items = {n: p for n, p in items.items() if n in uvr_config.include}
    items = {n: p for n, p in items.items() if n not in uvr_config.exclude}

    if not items:
        ui.console.print("No packages found.")
        return

    ui.console.print()
    ui.section("Packages")
    rows: list[list[str]] = []
    for name, pkg in sorted(items.items()):
        reason = changed_packages.reasons.get(name, "unchanged")
        baseline = baseline_tags.items.get(name)
        diff_from = baseline.raw if baseline else "(initial)"
        # `changed`/`unchanged` get colored badges; any other reason
        # (e.g. "new package") shows verbatim in dim — still padded so
        # columns line up with the badge kinds.
        if reason in _REASON_TO_BADGE:
            status_cell = ui.badge_markup(_REASON_TO_BADGE[reason])
        else:
            status_cell = f"[uvr.dim]{reason:<9}[/]"
        # Color the package name to match the badge: bright for changed,
        # dim for unchanged. Keeps the row visually unified.
        if reason == "changed":
            name_cell = f"[uvr.accent]{name}[/]"
        elif reason == "unchanged":
            name_cell = f"[uvr.dim]{name}[/]"
        else:
            name_cell = name
        rows.append([status_cell, name_cell, pkg.version.raw, diff_from])
    ui.print_table(["status", "package", "version", "diff from"], rows)

    if not changed_packages.reasons:
        ui.console.print()
        ui.hint("Nothing changed since last release.")
    else:
        ui.console.print()
        ui.hint("Next:", "uvr release --dry-run")
