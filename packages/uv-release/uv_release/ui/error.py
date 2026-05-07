"""ErrorBlock: red `error:` summary, indented detail rows, and a Fix section.

For *expected* failures the user can act on. The Fix section uses the same
section grammar as the rest of the CLI (`Fix\\n---\\n  cmd`) so users can
copy-paste the next commands. Don't use this for crashes — uncaught
exceptions get Rich's default traceback.
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
    commands shown under a `Fix` section header.
    """
    console.print(f"[uvr.err]error:[/] {summary}")
    if detail:
        # Align keys to the widest one so values form a vertical column.
        w = max(len(k) for k in detail)
        for k, v in detail.items():
            console.print(f"  {k:<{w}}  {v}")
    if fixes:
        console.print()
        # Inline section header — we can't import ui.section() because that
        # writes to stdout, while errors must stay on stderr.
        title = "Fix"
        console.print(title, style="uvr.title")
        console.print("-" * len(title), style="uvr.rule")
        for cmd in fixes:
            console.print(f"  [uvr.cmd]{cmd}[/]")
