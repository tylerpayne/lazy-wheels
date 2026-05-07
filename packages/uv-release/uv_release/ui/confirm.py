"""Confirm: bold question + magenta `[y/N]` hint.

Wraps `rich.prompt.Confirm.ask` so every uvr prompt looks the same. Default
is `False` so a bare Enter aborts; pass `--yes` on the command to skip.
"""

from __future__ import annotations

from rich.prompt import Confirm

from .console import console


def confirm(question: str, *, default: bool = False) -> bool:
    """Ask a yes/no question. Returns the user's answer."""
    # Wrap question in bold; Rich renders the [y/N] hint itself.
    return Confirm.ask(
        f"[bold]{question}[/]",
        default=default,
        console=console,
    )
