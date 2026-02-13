"""Shell and git utilities.

Provides simple wrappers around subprocess calls for running shell commands
and git operations, plus output formatting helpers.
"""

from __future__ import annotations

import subprocess
import sys


def git(*args: str, check: bool = True) -> str:
    """Run a git command and return stdout.

    Args:
        *args: Arguments to pass to git (e.g., "status", "--short").
        check: If True (default), raise on non-zero exit. Set to False
               for commands that may legitimately fail (e.g., tag lookup).

    Returns:
        Stripped stdout from the git command.
    """
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=check)
    return result.stdout.strip()


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    """Run an arbitrary shell command.

    Unlike git(), this doesn't capture output - it streams directly to
    the terminal so users can see build progress, etc.

    Args:
        *args: Command and arguments (e.g., "uv", "build", "pkg/").
        check: If True (default), raise on non-zero exit.

    Returns:
        CompletedProcess with returncode for checking success.
    """
    return subprocess.run(args, check=check)


def step(msg: str) -> None:
    """Print a visually distinct step header.

    Used to separate major phases of the release pipeline in terminal output.
    """
    print(f"\n{'─' * 60}\n{msg}\n{'─' * 60}")


def fatal(msg: str) -> None:
    """Print an error message and exit with code 1.

    Use for unrecoverable errors that should halt the pipeline.
    """
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)
