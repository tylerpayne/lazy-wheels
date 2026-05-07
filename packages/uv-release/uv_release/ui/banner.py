"""Banner: two-line opener for `uvr` (no args) or `uvr --help`.

One bold word + a tagline. No ASCII art logo, no figlet — those age badly
and make the tool feel hobbyist.
"""

from __future__ import annotations

from .console import console


def banner(
    version: str, tagline: str = "a release planner for python monorepos"
) -> None:
    console.print(f"[uvr.title]uvr[/] {version} [uvr.dim]·[/] {tagline}")
    console.print(
        "[uvr.dim]type[/] [uvr.cmd]help[/]"
        " [uvr.dim]for commands ·[/] [uvr.cmd]uvr release[/]"
        " [uvr.dim]for the demo[/]"
    )
