"""Lockfile sync command."""

from __future__ import annotations

import subprocess
from typing import Literal

from ..ui.console import console
from .base import Command


class SyncLockfileCommand(Command):
    """Regenerate uv.lock after pyproject.toml changes.

    Uses ``uv lock`` (not ``uv sync``) because the bump pipeline only needs
    the lockfile updated. ``uv sync`` also installs and can fail in CI on
    optional extras even when the lock itself is fine. We want this to fail
    loudly: if the lockfile cannot be regenerated, the bump commit would be
    inconsistent with pyproject.toml.
    """

    type: Literal["sync_lockfile"] = "sync_lockfile"

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        result = subprocess.run(["uv", "lock"])
        return result.returncode
