"""The ``uvr run`` command."""

from __future__ import annotations

import argparse


def cmd_run(args: argparse.Namespace) -> None:
    """Run the release pipeline locally (usually called from CI)."""
    # Late imports to allow patching via ``uv_release_monorepo.cli.<name>``.
    # Tests patch these names on the ``cli`` package; by looking them up at
    # call time through the package, the mock objects are picked up correctly.
    import uv_release_monorepo.cli as _cli

    if getattr(args, "plan", None):
        from uv_release_monorepo.models import ReleasePlan

        plan = ReleasePlan.model_validate_json(args.plan)
        _cli.execute_plan(plan, push=not args.no_push)
    else:
        _cli.run_pipeline(
            rebuild_all=args.rebuild_all,
            push=not args.no_push,
            dry_run=args.dry_run,
        )
