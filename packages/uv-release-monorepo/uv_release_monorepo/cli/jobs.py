"""CI workflow job commands (``uvr jobs validate/build/release/bump``)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..shared.utils.cli import resolve_plan_json
from ..shared.models import ReleasePlan
from ..shared.executor import ReleaseExecutor
from ..shared.hooks import load_hook


def cmd_validate_plan(args: argparse.Namespace) -> None:
    """Validate and pretty-print the release plan."""
    plan = ReleasePlan.model_validate_json(resolve_plan_json(args.plan))
    print(json.dumps(plan.model_dump(mode="json"), indent=2))


def cmd_build(args: argparse.Namespace) -> None:
    """Build packages for a runner."""
    plan_obj = ReleasePlan.model_validate_json(resolve_plan_json(args.plan))
    hook = load_hook(Path.cwd())
    ReleaseExecutor(plan_obj, hook).build(runner=args.runner)


def cmd_release(args: argparse.Namespace) -> None:
    """Tag, create GitHub releases, and push release tags."""
    plan_obj = ReleasePlan.model_validate_json(resolve_plan_json(args.plan))
    hook = load_hook(Path.cwd())
    ReleaseExecutor(plan_obj, hook).publish()


def cmd_download(args: argparse.Namespace) -> None:
    """Download wheels for all changed packages into dist/."""
    import os
    import sys

    from ..shared.models import DownloadWheelsCommand

    plan_obj = ReleasePlan.model_validate_json(resolve_plan_json(args.plan))

    from pathlib import Path

    from packaging.utils import canonicalize_name

    # Check if wheels already exist locally (e.g. local build)
    dist = Path("dist")
    if dist.is_dir():
        all_present = True
        for name, pkg in plan_obj.changed.items():
            dist_name = canonicalize_name(name).replace("-", "_")
            pattern = f"{dist_name}-{pkg.release_version}-*.whl"
            if not list(dist.glob(pattern)):
                all_present = False
                break
        if all_present:
            print("All wheels already in dist/, skipping download.")
            return

    # Use reuse_run_id if set, otherwise fall back to current run
    run_id = plan_obj.reuse_run_id or os.environ.get("GITHUB_RUN_ID")
    if not run_id:
        print(
            "ERROR: No run ID and wheels not in dist/. "
            "Set --reuse-run or run in GitHub Actions.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build the packages dict: name → release tag (for fallback)
    packages = {
        name: f"{name}/v{pkg.release_version}" for name, pkg in plan_obj.changed.items()
    }

    cmd = DownloadWheelsCommand(
        packages=packages,
        run_id=run_id,
        directory="dist",
        label="Download release wheels",
    )
    result = cmd.execute()
    if result.returncode != 0:
        print("ERROR: Failed to download wheels.", file=sys.stderr)
        sys.exit(1)


def cmd_bump(args: argparse.Namespace) -> None:
    """Bump versions, commit, baseline tags, and push."""
    plan_obj = ReleasePlan.model_validate_json(resolve_plan_json(args.plan))
    hook = load_hook(Path.cwd())
    ReleaseExecutor(plan_obj, hook).bump()
