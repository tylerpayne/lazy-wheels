"""Singleton Console + named theme.

Every other ui module imports `console` from here so styling stays in one
place. Names map to the design grammar in the spec — anywhere you'd reach
for a literal color (`bright_magenta`, `bright_yellow`), use the named style
instead so we can retune all of uvr at once.
"""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme


THEME = Theme(
    {
        # Brand. The bold-magenta header is uvr's signature.
        "uvr.title": "bold bright_magenta",
        "uvr.accent": "bright_magenta",
        # State badges. Word carries meaning even when color is stripped.
        "uvr.changed": "bright_yellow",
        "uvr.unchanged": "dim",
        "uvr.stale": "red",
        "uvr.clean": "green",
        "uvr.created": "green",
        "uvr.updated": "green",
        "uvr.error": "red",
        # Inline emphasis.
        "uvr.cmd": "bright_magenta",
        "uvr.path": "bright_magenta",
        "uvr.value": "cyan",
        "uvr.dim": "dim",
        "uvr.ok": "green",
        "uvr.err": "bold red",
        "uvr.rule": "dim",
    }
)


# Single shared console. Don't instantiate Rich's Console anywhere else;
# multiple consoles fight over the terminal during Live/Status renders.
console = Console(theme=THEME, highlight=False, soft_wrap=False)

# Dedicated stderr console for error blocks. Rich shares a single Live
# region across calls, so a separate Console keeps stderr isolated from
# stdout's status/progress widgets.
err_console = Console(theme=THEME, highlight=False, soft_wrap=False, stderr=True)
