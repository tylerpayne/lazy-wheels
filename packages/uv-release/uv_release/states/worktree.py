"""Parse git worktree state."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..git import GitRepo
from ..types import GitState


def parse_git_state() -> GitState:
    """Read repository state for validation."""
    repo = GitRepo()
    return GitState(
        is_dirty=repo.is_dirty(),
        is_ahead_or_behind=repo.is_ahead_or_behind(),
    )


def has_uncommitted_changes(path: Path) -> bool:
    """Check whether a file has uncommitted changes via git diff."""
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", str(path)],
        capture_output=True,
    )
    return result.returncode != 0
