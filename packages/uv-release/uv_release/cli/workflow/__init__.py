"""Workflow subcommand dispatch."""

from __future__ import annotations

import argparse

from .init import cmd_init, cmd_upgrade


def cmd_init_dispatch(args: argparse.Namespace) -> None:
    """Route to init or upgrade based on --upgrade flag."""
    if getattr(args, "upgrade", False):
        cmd_upgrade(args)
    else:
        cmd_init(args)
