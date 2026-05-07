"""Pipeline: two-level indented step list with magenta arrow routes.

Used any time something flows from A to B (package → registry, version →
version, baseline → head). Step name in cyan, route source/destination
separated by a magenta arrow.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .console import console


@dataclass(frozen=True)
class Route:
    src: str
    dst: str


@dataclass(frozen=True)
class Step:
    name: str
    routes: tuple[Route, ...] = ()


def pipeline(steps: Iterable[Step]) -> None:
    """Render each step on its own line, with optional indented routes.

    Padding is calculated so every step name + route source aligns to the
    widest source in the whole step list.
    """
    steps = list(steps)
    # Align route sources to the widest src across all routes so arrows
    # form a single vertical column when there are multiple routes.
    src_width = max(
        (len(r.src) for s in steps for r in s.routes),
        default=0,
    )
    for s in steps:
        console.print(f"  run   [uvr.value]{s.name}[/]")
        for r in s.routes:
            console.print(f"        {r.src:<{src_width}} [uvr.accent]→[/] {r.dst}")
