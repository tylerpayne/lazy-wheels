"""Skill subcommand dispatch."""

from __future__ import annotations

import argparse

from .init import cmd_skill_init, cmd_skill_upgrade


def cmd_skill_dispatch(args: argparse.Namespace) -> None:
    """Route to init or upgrade based on --upgrade flag."""
    if getattr(args, "upgrade", False):
        cmd_skill_upgrade(args)
    else:
        cmd_skill_init(args)
