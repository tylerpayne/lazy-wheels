"""Confirm: bold question + magenta `[y/N]` hint.

Custom (not `rich.prompt.Confirm.ask`) so the prompt reads exactly
`Apply fix? [y/N]: ` — capital letter marks the universally-recognized
default and only the `[y/N]` token is brand-colored. Rich's stock prompt
renders `[y/n] (n)` with the default shown twice and the `(n)` styled
as a "value" (cyan in our theme), which collides with our color language.
"""

from __future__ import annotations

from .console import console


def confirm(question: str, *, default: bool = False) -> bool:
    """Ask a yes/no question. Returns the user's answer.

    Bare Enter returns the default; everything other than `y`/`yes`
    (case-insensitive) is treated as no.
    """
    # Capitalize the default in the hint so `(y/N)` reads as "no by default"
    # the way every CLI does. Parens (not square brackets) so Rich's markup
    # parser doesn't try to read them as a style tag.
    choices = "(Y/n)" if default else "(y/N)"
    prompt = f"[bold]{question}[/] [uvr.cmd]{choices}[/]: "
    while True:
        try:
            # console.input renders Rich markup in the prompt and reads
            # one line of input from stdin.
            answer = console.input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return False
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        # Re-prompt on garbage input rather than silently treating it as no.
        console.print("Please answer 'y' or 'n'.")
