"""The ``uvr skill init`` and ``uvr skill init --upgrade`` commands."""

from __future__ import annotations

import argparse

from ._args import CommandArgs, compute_plan_or_exit
from ..intents.upgrade_skill import UpgradeSkillIntent
from ..execute import execute_plan


class SkillInitArgs(CommandArgs):
    """Typed arguments for ``uvr skill init``."""

    force: bool = False
    upgrade: bool = False
    base_only: bool = False
    editor: str | None = None


def cmd_skill_dispatch(args: argparse.Namespace) -> None:
    """Route to init or upgrade based on --upgrade flag."""
    if getattr(args, "upgrade", False):
        cmd_skill_upgrade(args)
    else:
        cmd_skill_init(args)


def cmd_skill_init(args: argparse.Namespace) -> None:
    """Copy bundled Claude Code skills into the current project."""
    parsed = SkillInitArgs.from_namespace(args)

    intent = UpgradeSkillIntent(
        force=parsed.force,
        upgrade=False,
        base_only=parsed.base_only,
        editor=parsed.editor,
    )

    plan = compute_plan_or_exit(intent)

    execute_plan(plan, hooks=None)

    version = plan.metadata.uvr_state.uvr_version if plan.metadata.uvr_state else ""
    if parsed.base_only:
        print(f"OK: Wrote merge bases for skills (uvr v{version})")
    else:
        print(f"OK: Skills initialized (uvr v{version})")
        print()
        print("Next steps:")
        print("  1. Review .claude/skills/release/SKILL.md and tailor to your project")
        print("  2. Commit the skill files")
        print("  3. Use /release in Claude Code to start a release")


def cmd_skill_upgrade(args: argparse.Namespace) -> None:
    """Upgrade skill files via three-way merge."""
    parsed = SkillInitArgs.from_namespace(args)

    intent = UpgradeSkillIntent(
        force=False,
        upgrade=True,
        base_only=False,
        editor=parsed.editor,
    )

    plan = compute_plan_or_exit(intent)

    execute_plan(plan, hooks=None)

    version = plan.metadata.uvr_state.uvr_version if plan.metadata.uvr_state else ""
    print(f"OK: Skill upgrade complete (uvr v{version})")
