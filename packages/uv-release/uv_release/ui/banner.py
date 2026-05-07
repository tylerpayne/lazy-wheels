"""Banner: one-line opener for `uvr` (no args) or `uvr --help`.

One bold word + a tagline. No ASCII art logo, no figlet — those age badly
and make the tool feel hobbyist.
"""

from __future__ import annotations

from .console import console


def banner(version: str, tagline: str = "Release management for uv workspaces") -> None:
    console.print(f"[uvr.title]uvr[/] {version}  {tagline}")
