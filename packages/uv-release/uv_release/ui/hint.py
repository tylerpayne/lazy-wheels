"""Hint: dim trailing line that points at the next command.

Every successful command should end with a hint or a blank line. Hints
embed the literal next command in magenta so the user can copy-paste it
without retyping.
"""

from __future__ import annotations

from .console import console


def hint(text: str, cmd: str | None = None) -> None:
    if cmd is None:
        console.print(f"  [uvr.dim]{text}[/]")
        return
    # Split text on the placeholder if present, else append cmd at the end.
    if "{cmd}" in text:
        before, _, after = text.partition("{cmd}")
        console.print(f"  [uvr.dim]{before}[/][uvr.cmd]{cmd}[/][uvr.dim]{after}[/]")
    else:
        console.print(f"  [uvr.dim]{text}[/] [uvr.cmd]{cmd}[/]")
