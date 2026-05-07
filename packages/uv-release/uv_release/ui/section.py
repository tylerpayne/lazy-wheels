"""Section: bold-magenta title + matching-length hyphen rule.

The opener for every distinct phase of a command. Custom (not Rich's Rule)
so we get a literal hyphen rule instead of Unicode box characters — that's
what makes uvr output look like `--help` text.
"""

from __future__ import annotations

from .console import console


def section(title: str) -> None:
    # markup=False so titles like "Configuration ([tool.uvr.config])" render
    # the brackets as literal text instead of being parsed as Rich markup.
    console.print(title, style="uvr.title", markup=False)
    # Hyphen run sized to the title so the rule sits flush under it.
    console.print("-" * len(title), style="uvr.rule")
