"""Shell utilities: output formatting, progress, and error helpers."""

from __future__ import annotations

import sys
import time


def print_step(msg: str) -> None:
    """Print a visually distinct step header.

    Used to separate major phases of the release pipeline in terminal output.
    """
    print(f"\n{'─' * 60}\n{msg}\n{'─' * 60}")


def exit_fatal(msg: str) -> None:
    """Print an error message and exit with code 1.

    Use for unrecoverable errors that should halt the pipeline.
    """
    # Clear any in-progress progress bar line
    sys.stderr.write("\r" + " " * 70 + "\r")
    sys.stderr.flush()
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


_BAR_WIDTH = 20
_CHART_WIDTH = 10


def _format_duration(secs: float) -> str:
    """Format a duration with appropriate precision."""
    ms = secs * 1000
    if ms >= 1:
        return f"{int(ms)}ms"
    us = secs * 1_000_000
    if us >= 1:
        return f"{us:.0f}us"
    ns = secs * 1_000_000_000
    return f"{ns:.0f}ns"


class Progress:
    """ASCII progress bar reporter.

    Shows ``[###-----] message...`` on stderr during execution.
    On finish, prints a bar chart summary with per-phase timing to stdout.
    """

    def __init__(self, total_steps: int) -> None:
        self._start = time.monotonic()
        self._step_start = self._start
        self._completed: list[tuple[str, float]] = []  # (summary, seconds)
        self._total = total_steps
        self._current = 0

    def _render_bar(self) -> str:
        filled = int(_BAR_WIDTH * self._current / self._total) if self._total else 0
        return "#" * filled + "-" * (_BAR_WIDTH - filled)

    def update(self, msg: str) -> None:
        """Show progress bar with current step message."""
        bar = self._render_bar()
        sys.stderr.write(f"\r  [{bar}] {msg}...".ljust(70))
        sys.stderr.flush()
        self._step_start = time.monotonic()

    def complete(self, summary: str) -> None:
        """Record a completed step and advance the bar."""
        elapsed = time.monotonic() - self._step_start
        self._completed.append((summary, elapsed))
        self._current += 1
        bar = self._render_bar()
        sys.stderr.write(
            f"\r  [{bar}] {summary} ({_format_duration(elapsed)})".ljust(70)
        )
        sys.stderr.flush()
        self._step_start = time.monotonic()

    def finish(self, *, header: str = "Planning", release_count: int = 0) -> None:
        """Clear the progress bar and print a bar chart summary."""
        # Total from sum of completed steps (not wall clock)
        # so reported total matches the sum of individual steps
        total = sum(s for _, s in self._completed)
        sys.stderr.write("\r" + " " * 70 + "\r")
        sys.stderr.flush()

        max_secs = max((s for _, s in self._completed), default=0.001) or 0.001

        print()
        print(header)
        print("-" * len(header))
        for summary, secs in self._completed:
            filled = round(_CHART_WIDTH * secs / max_secs)
            bar = "#" * filled + "-" * (_CHART_WIDTH - filled)
            print(f"  |{bar}| {summary} ({_format_duration(secs)})")
        s = "s" if release_count != 1 else ""
        print(f"  Planned {release_count} release{s} in {_format_duration(total)}")
