"""The ``uvr clean`` command."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ._args import CommandArgs


class CleanArgs(CommandArgs):
    """Typed arguments for ``uvr clean``."""


def cmd_clean(args: argparse.Namespace) -> None:
    """Remove uvr caches and ephemeral files."""
    _parsed = CleanArgs.from_namespace(args)
    removed: list[str] = []

    for cache in (Path.home() / ".uvr" / "cache", Path.cwd() / ".uvr" / "cache"):
        if cache.is_dir():
            shutil.rmtree(cache)
            removed.append(str(cache))

    if removed:
        for p in removed:
            print(f"  removed {p}")
        print(f"\nCleaned {len(removed)} location(s).")
    else:
        print("Nothing to clean.")
