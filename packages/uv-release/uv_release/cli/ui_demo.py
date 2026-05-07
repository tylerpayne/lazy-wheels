"""Visual showcase of the uv_release.ui design system.

Renders every primitive in isolation, then a composed `uvr release` flow.
Run with `uvr ui-demo` to verify styling end-to-end after touching the ui
module — this is the visual analogue of a snapshot test.
"""

from __future__ import annotations

import time

from .. import ui


def cmd_ui_demo() -> None:
    _demo_banner()
    _demo_section()
    _demo_progress_lines()
    _demo_table()
    _demo_badges()
    _demo_pipeline()
    _demo_kv()
    _demo_hint()
    _demo_error()
    _demo_spinner()
    _demo_full_flow()


def _demo_banner() -> None:
    ui.banner("0.4.2")
    ui.console.print()


def _demo_section() -> None:
    ui.section("Section")
    ui.console.print("  The opener for every distinct phase.")
    ui.console.print("  Bold-magenta title + matching-length hyphen rule.")
    ui.console.print()


def _demo_progress_lines() -> None:
    ui.section("ProgressLine")
    with ui.progress_lines() as p:
        # Realistic-looking timings; advance just enough to show the bar move.
        for desc, total in [
            ("Discovered 3 packages", 3),
            ("Resolved 3 baselines", 3),
            ("Detected 2 changed", 2),
            ("Computed versions", 2),
        ]:
            t = p.add_task(desc, total=total)
            for _ in range(total):
                time.sleep(0.05)
                p.advance(t)
    ui.console.print()


def _demo_table() -> None:
    ui.section("Table")
    ui.print_table(
        ["status", "package", "version", "previous"],
        [
            [
                ui.badge_markup("changed"),
                "[uvr.accent]my-core[/]",
                "0.1.0 → [b]0.2.0[/]",
                "0.1.0",
            ],
            [
                ui.badge_markup("changed"),
                "[uvr.accent]my-auth[/]",
                "0.1.0 → [b]0.1.1[/]",
                "0.1.0",
            ],
            [
                ui.badge_markup("unchanged"),
                "[uvr.dim]my-api[/]",
                "0.4.2",
                "0.4.2",
            ],
            [
                ui.badge_markup("unchanged"),
                "[uvr.dim]my-cli[/]",
                "1.0.0",
                "1.0.0",
            ],
        ],
    )
    ui.console.print()


def _demo_badges() -> None:
    ui.section("StatusBadge")
    pairs = [
        ("changed", "[uvr.accent]my-core[/]"),
        ("unchanged", "[uvr.dim]my-api[/]"),
        ("stale", "[uvr.accent]my-auth/pyproject.toml[/]"),
        ("clean", "branch [uvr.value]main[/]"),
        ("created", ".uvr.toml"),
        ("updated", "my-auth/pyproject.toml"),
        ("error", "stale pin in my-auth/pyproject.toml"),
    ]
    for kind, target in pairs:
        ui.console.print(f"  {ui.badge_markup(kind)} {target}")
    ui.console.print()


def _demo_pipeline() -> None:
    ui.section("Pipeline")
    ui.pipeline(
        [
            ui.Step(name="uvr-build"),
            ui.Step(
                name="uvr-publish",
                routes=(
                    ui.Route(src="my-core", dst="pypi"),
                    ui.Route(src="my-auth", dst="pypi"),
                    ui.Route(src="my-api", dst="ghcr.io"),
                ),
            ),
        ]
    )
    ui.console.print()


def _demo_kv() -> None:
    ui.section("KV")
    ui.kv(
        {
            "baseline": "[uvr.value]v0.4.1[/]",
            "strategy": "conventional",
            "branch": "[uvr.value]main[/] · 3 ahead of [uvr.value]origin/main[/]",
            "tagged": "2d ago",
            "packages": "4 ([b]2 changed[/])",
        }
    )
    ui.console.print()


def _demo_hint() -> None:
    ui.section("Hint")
    ui.hint("Next:", "uvr release")
    ui.hint("See {cmd} to verify.", "uvr pin --check")
    ui.hint("Hint: pass {cmd} to skip the prompt.", "-y")
    ui.console.print()


def _demo_error() -> None:
    ui.section("ErrorBlock")
    ui.error(
        "stale pin in [uvr.accent]my-auth/pyproject.toml[/]",
        detail={
            "expected": "my-core ^0.2",
            "got": "my-core ^0.1",
        },
        fixes=[
            "uvr pin --update",
            "git commit -am 'pin my-core'",
        ],
    )
    ui.console.print()


def _demo_spinner() -> None:
    ui.section("Spinner")
    with ui.spinner("Fetching baseline tags", "git ls-remote origin") as s:
        time.sleep(0.6)
        s.update("Resolving from PyPI     [uvr.dim]my-core, my-auth[/]")
        time.sleep(0.6)
        s.update("Pushing tags to origin  [uvr.dim]2 tags[/]")
        time.sleep(0.6)
    ui.spinner_done("Fetched baseline tags", elapsed_ms=214)
    ui.console.print()


def _demo_full_flow() -> None:
    """The full `uvr release` composition from the spec."""
    ui.console.print("[uvr.dim]$[/] uvr release")
    ui.console.print()
    ui.section("Planning")
    with ui.progress_lines() as p:
        for desc, total in [
            ("Discovered 4 packages", 4),
            ("Resolved 4 baselines", 4),
            ("Detected 2 changed, 2 unchanged", 4),
            ("Computed versions", 2),
        ]:
            t = p.add_task(desc, total=total)
            for _ in range(total):
                time.sleep(0.04)
                p.advance(t)
    ui.console.print("  Planned 2 releases in [b]16ms[/]")
    ui.console.print()

    ui.section("Packages")
    ui.print_table(
        ["status", "package", "version", "previous"],
        [
            [
                ui.badge_markup("changed"),
                "[uvr.accent]my-core[/]",
                "0.1.0 → [b]0.2.0[/]",
                "0.1.0",
            ],
            [
                ui.badge_markup("changed"),
                "[uvr.accent]my-auth[/]",
                "0.1.0 → [b]0.1.1[/]",
                "0.1.0",
            ],
            [
                ui.badge_markup("unchanged"),
                "[uvr.dim]my-api[/]",
                "0.4.2",
                "0.4.2",
            ],
            [
                ui.badge_markup("unchanged"),
                "[uvr.dim]my-cli[/]",
                "1.0.0",
                "1.0.0",
            ],
        ],
    )
    ui.console.print()

    ui.section("Pipeline")
    ui.pipeline(
        [
            ui.Step(name="uvr-build"),
            ui.Step(
                name="uvr-publish",
                routes=(
                    ui.Route(src="my-core", dst="pypi"),
                    ui.Route(src="my-auth", dst="pypi"),
                ),
            ),
        ]
    )
    ui.console.print()
    # Demo only — don't actually block on stdin. `[y/N]` must be escaped so
    # Rich does not interpret it as a style tag.
    ui.console.print(r"[bold]Dispatch release?[/] [uvr.cmd]\[y/N][/] [uvr.cmd]█[/]")
