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
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


_BAR_WIDTH = 20


class Progress:
    """ASCII progress bar reporter.

    Shows ``STEP [###-----] message...`` on stderr during execution.
    On finish, prints a detailed summary with per-phase timing to stdout.
    """

    def __init__(self, total_steps: int) -> None:
        self._start = time.monotonic()
        self._step_start = self._start
        self._completed: list[tuple[str, int]] = []
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
        elapsed_ms = int((time.monotonic() - self._step_start) * 1000)
        self._completed.append((summary, elapsed_ms))
        self._current += 1
        bar = self._render_bar()
        sys.stderr.write(f"\r  [{bar}] {summary} ({elapsed_ms}ms)".ljust(70))
        sys.stderr.flush()
        self._step_start = time.monotonic()

    def finish(self, *, header: str = "Planning") -> None:
        """Clear the progress bar and print the detailed summary."""
        total_ms = int((time.monotonic() - self._start) * 1000)
        sys.stderr.write("\r" + " " * 70 + "\r")
        sys.stderr.flush()
        print()
        print(header)
        print("-" * len(header))
        for summary, ms in self._completed:
            print(f"  {summary} ({ms}ms)")
        print(f"  Resolved in {total_ms}ms")
