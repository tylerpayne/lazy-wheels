"""The ``uvr build`` command — build workspace packages locally."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from ._args import CommandArgs
from ..shared.models import PlanConfig
from ..shared.utils.cli import __version__, read_matrix


class BuildArgs(CommandArgs):
    """Typed arguments for ``uvr build``."""

    rebuild_all: bool = False
    packages: list[str] | None = None
    python_version: str = "3.12"


def cmd_build(args: argparse.Namespace) -> None:
    """Build changed workspace packages using layered dependency ordering."""
    parsed = BuildArgs.from_namespace(args)
    root = Path.cwd()

    from ..shared.context import build_context
    from ..shared.executor import ReleaseExecutor
    from ..shared.hooks import load_hook
    from ..shared.planner import ReleasePlanner
    from ..shared.utils.shell import Progress

    package_runners = read_matrix(root)
    hook = load_hook(root)

    # Suppress planner discovery output
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    progress = Progress(total_steps=5)
    try:
        ctx = build_context(progress=progress)

        config = PlanConfig(
            rebuild_all=parsed.rebuild_all,
            matrix=package_runners,
            uvr_version=__version__,
            python_version=parsed.python_version,
            rebuild=parsed.packages or [],
            restrict_packages=parsed.packages or [],
            ci_publish=False,
            dev_release=True,
            dry_run=True,
        )
        if hook:
            config = hook.pre_plan(config)

        plan = ReleasePlanner(config, ctx, progress=progress).plan()
    finally:
        sys.stdout = old_stdout

    if not plan.changed:
        print("Nothing to build — no packages have changed since last release.")
        print("Use --rebuild-all to build all packages.")
        return

    if hook:
        plan = hook.post_plan(plan)

    # Print what we're building
    nw = max(len(n) for n in plan.changed)
    print(f"Building {len(plan.changed)} package(s):\n")
    for name in sorted(plan.changed):
        pkg = plan.changed[name]
        print(f"  {name.ljust(nw)}  {pkg.current_version}")

    # Show build layers (deduplicate across runners for local builds)
    if plan.build_commands:
        shown: set[str] = set()
        for runner_key, stages in plan.build_commands.items():
            layer = 0
            for stage in stages:
                if stage.packages:
                    pkgs = ", ".join(sorted(stage.packages))
                    key = f"{layer}:{pkgs}"
                    if key not in shown:
                        print(f"  layer {layer}: {pkgs}")
                        shown.add(key)
                    layer += 1

    print()
    ReleaseExecutor(plan, hook).build()
    print(f"\nBuilt {len(plan.changed)} package(s) into dist/")
