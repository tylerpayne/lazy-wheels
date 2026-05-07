"""Table: no-box, dim-uppercase header, space-padded columns.

Wraps `rich.table.Table` with the box style turned off. Boxes — even
`SIMPLE` — fight the hyphen-rule grammar from `section()`, so we use space
padding instead.
"""

from __future__ import annotations

from collections.abc import Iterable

from rich.table import Table

from .console import console


def make_table(*headers: str) -> Table:
    """Construct a styled, box-less Table.

    Caller adds rows with `.add_row(...)`. Pass it to `print_table` or
    `console.print` directly — both work.
    """
    t = Table(
        box=None,
        pad_edge=False,
        show_edge=False,
        header_style="uvr.dim",
        padding=(0, 2),
    )
    for h in headers:
        t.add_column(h.upper())
    return t


def print_table(headers: Iterable[str], rows: Iterable[Iterable[str]]) -> None:
    """Convenience: build + print in one call. Each row is a list of cells.

    Cell strings may contain Rich markup (e.g. `"[uvr.changed]changed[/]"`).
    """
    t = make_table(*headers)
    for row in rows:
        t.add_row(*list(row))
    console.print(t)
