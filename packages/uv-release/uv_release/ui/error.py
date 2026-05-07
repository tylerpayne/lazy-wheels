"""ErrorBlock: red `error:` summary, indented detail rows, and fix commands.

For *expected* failures the user can act on. Always end with a `fix →`
block so the user can copy-paste the next command. Don't use this for
crashes — uncaught exceptions get Rich's default traceback.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .console import err_console as console


def error(
    summary: str,
    *,
    detail: Mapping[str, str] | None = None,
    fixes: Sequence[str] | None = None,
) -> None:
    """Print an error block.

    `detail` is a key/value mapping (e.g. `{"expected": "...", "got": "..."}`)
    rendered as aligned indented pairs. `fixes` is a list of copy-pasteable
    commands; the first gets the `fix →` lead, the rest are aligned under it.
    """
    console.print(f"[uvr.err]error:[/] {summary}")
    if detail:
        # Align keys to the widest one so values form a vertical column.
        w = max(len(k) for k in detail)
        for k, v in detail.items():
            console.print(f"  {k:<{w}}  {v}")
    if fixes:
        console.print()
        for i, cmd in enumerate(fixes):
            lead = "  fix" if i == 0 else "     "
            console.print(f"{lead} [uvr.accent]→[/] {cmd}")
