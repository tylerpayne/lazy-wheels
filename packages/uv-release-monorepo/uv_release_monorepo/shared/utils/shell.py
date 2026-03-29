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


class Progress:
    """Simple ASCII progress reporter that overwrites the current line."""

    def __init__(self) -> None:
        self._start = time.monotonic()
        self._step_start = self._start
        self._steps: list[str] = []

    def update(self, msg: str) -> None:
        """Print a progress step, overwriting the previous line."""
        self._steps.append(msg)
        sys.stderr.write(f"\r  {msg}...".ljust(60))
        sys.stderr.flush()
        self._step_start = time.monotonic()

    def finish(self, *, package_count: int, changed_count: int) -> None:
        """Clear the progress line and print the summary."""
        elapsed_ms = int((time.monotonic() - self._start) * 1000)
        sys.stderr.write("\r" + " " * 60 + "\r")
        sys.stderr.flush()
        print(
            f"Computed changes across {package_count} packages "
            f"({changed_count} changed) in {elapsed_ms}ms"
        )
