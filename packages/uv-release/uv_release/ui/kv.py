"""KV: two-column aligned key/value pairs.

Keys are dim, padded to the widest key. Values are printed as-is and may
contain Rich markup. Used for status summaries and config display.
"""

from __future__ import annotations

from collections.abc import Mapping

from .console import console


def kv(pairs: Mapping[str, str]) -> None:
    if not pairs:
        return
    w = max(len(k) for k in pairs)
    for k, v in pairs.items():
        console.print(f"  [uvr.dim]{k:<{w}}[/]  {v}")
