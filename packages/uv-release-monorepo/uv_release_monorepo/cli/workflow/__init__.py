"""Workflow management subcommands (init, upgrade, validate, runners, publish)."""

from __future__ import annotations

import argparse

from .init import cmd_init, cmd_upgrade
from .publish import cmd_publish_config
from .runners import cmd_runners
from .validate import cmd_validate


def cmd_init_dispatch(args: argparse.Namespace) -> None:
    """Route to cmd_init or cmd_upgrade based on --upgrade flag."""
    if getattr(args, "upgrade", False):
        cmd_upgrade(args)
    else:
        cmd_init(args)


__all__ = [
    "cmd_init",
    "cmd_init_dispatch",
    "cmd_publish_config",
    "cmd_runners",
    "cmd_upgrade",
    "cmd_validate",
]
