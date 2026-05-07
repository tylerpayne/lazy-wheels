"""StatusBadge: padded one-word status token.

The token's text alone communicates state — color is decoration, so badges
remain readable when output is piped or color is stripped. All known badge
kinds are padded to the widest name so columns of badges align.
"""

from __future__ import annotations

from rich.text import Text


_STYLES: dict[str, str] = {
    "changed": "uvr.changed",
    "unchanged": "uvr.unchanged",
    "stale": "uvr.stale",
    "clean": "uvr.clean",
    "created": "uvr.created",
    "updated": "uvr.updated",
    "error": "uvr.error",
}

# Pad every badge to the widest known kind so they line up in tables and
# left-aligned columns. Computed once at import.
_WIDTH: int = max(len(k) for k in _STYLES)


def badge(kind: str) -> Text:
    """Return a styled `Text` for the given state token."""
    if kind not in _STYLES:
        msg = f"Unknown badge kind: {kind!r}. Known: {sorted(_STYLES)}"
        raise ValueError(msg)
    return Text(f"{kind:<{_WIDTH}}", style=_STYLES[kind])


def badge_markup(kind: str) -> str:
    """Markup-string variant for use inside table cells.

    Returns e.g. `"[uvr.changed]changed  [/]"` — pre-padded, ready to drop
    into `Table.add_row(...)`.
    """
    if kind not in _STYLES:
        msg = f"Unknown badge kind: {kind!r}. Known: {sorted(_STYLES)}"
        raise ValueError(msg)
    return f"[{_STYLES[kind]}]{kind:<{_WIDTH}}[/]"
