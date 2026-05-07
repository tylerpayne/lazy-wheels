"""ProgressLine: fixed-10-cell ASCII bar (`|##---|`), label, dim elapsed time.

Use one per discrete unit of work; let them stack inside a `section()`. The
ASCII glyphs (`#`, `-`) are deliberate — Rich's default is Unicode blocks
(▰▱) which look great but break in CI logs and screenshots pasted into
README code fences.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from rich.progress import (
    Progress,
    ProgressColumn,
    TextColumn,
)
from rich.text import Text

from .console import console

if TYPE_CHECKING:
    from rich.progress import Task


class _AsciiBarColumn(ProgressColumn):
    """Bar rendered as `  |##########|` — `#` and `-` framed by literal pipes.

    Rich joins columns with a space separator, so the pipes live inside the
    same column as the bar to get the tight `|##---|` look from the spec.
    The two-space indent lives here too. We extend ProgressColumn directly
    (not BarColumn) because BarColumn returns a `ProgressBar`, but we want
    plain `Text` for the ASCII glyphs.
    """

    def __init__(self, bar_width: int = 10) -> None:
        super().__init__()
        self.bar_width = bar_width

    def render(self, task: Task) -> Text:
        width = self.bar_width
        completed = task.completed or 0
        total = task.total or 0
        if total <= 0:
            filled = 0
        else:
            filled = int(width * (completed / total))
            filled = max(0, min(width, filled))
        bar = Text("  |")
        bar.append("#" * filled, style="uvr.accent")
        bar.append("-" * (width - filled), style="uvr.dim")
        bar.append("|")
        return bar


class _SmallElapsedColumn(ProgressColumn):
    """Elapsed time formatted like `9ms` / `57µs` / `1.2s`.

    Rich's TimeElapsedColumn renders `H:MM:SS` which is too coarse for
    sub-second pipeline stages. This shows the smallest sensible unit so
    fast stages don't all read as `0:00:00`.
    """

    def render(self, task: Task) -> Text:
        elapsed = task.finished_time if task.finished else task.elapsed
        if elapsed is None:
            return Text("--", style="uvr.dim")
        if elapsed < 1e-3:
            label = f"{elapsed * 1e6:.0f}µs"
        elif elapsed < 1:
            label = f"{elapsed * 1e3:.0f}ms"
        else:
            label = f"{elapsed:.1f}s"
        return Text(label, style="uvr.dim")


@contextmanager
def progress_lines() -> Iterator[Progress]:
    """Group multiple ProgressLine tasks into one Live region.

    Use this when you have several stacked stages and want them all to
    animate together. `add_task(...)` and `advance(...)` work exactly as
    `rich.progress.Progress` documents.
    """
    columns: list[ProgressColumn] = [
        _AsciiBarColumn(bar_width=10),
        TextColumn("{task.description}"),
        _SmallElapsedColumn(),
    ]
    with Progress(*columns, console=console, transient=False) as p:
        yield p


def progress_line(label: str, total: int = 1) -> None:
    """Render a single completed ProgressLine without animation.

    The non-streaming variant: label + full bar + (no elapsed). Useful for
    after-the-fact summaries where you already know the work is done.
    """
    bar_text = Text("#" * 10, style="uvr.accent")
    line = Text("  |")
    line.append(bar_text)
    line.append("|")
    line.append(f" {label}")
    # Total parameter kept for future use; presently we only render the
    # full bar since this is the non-animated path.
    _ = total
    console.print(line)
