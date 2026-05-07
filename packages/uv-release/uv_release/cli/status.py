"""uvr status: show workspace package status."""

from __future__ import annotations

from diny import inject

from .. import ui
from ..dependencies.config.uvr_config import UvrConfig
from ..dependencies.shared.baseline_tags import BaselineTags
from ..dependencies.shared.changed_packages import ChangedPackages
from ..dependencies.shared.workspace_packages import WorkspacePackages


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
        reason = changed_packages.reasons.get(name)
        baseline = baseline_tags.items.get(name)
        diff_from = baseline.raw if baseline else "(initial)"
        # ChangedPackages reasons are specific ("files changed", "dependency
        # changed", "initial release"); we collapse them to the badge column
        # and keep the verbose reason as a dim suffix on the package name so
        # users can still tell *why* a package changed.
        if reason is None:
            status_cell = ui.badge_markup("unchanged")
            name_cell = name
        else:
            status_cell = ui.badge_markup("changed")
            name_cell = f"[uvr.accent]{name}[/] ({reason})"
        rows.append([status_cell, name_cell, pkg.version.raw, diff_from])
    ui.print_table(["status", "package", "version", "diff from"], rows)

    if not changed_packages.reasons:
        ui.console.print()
        ui.hint("Nothing changed since last release.")
