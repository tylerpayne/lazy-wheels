"""The ``uvr release`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..models import JOB_ORDER, ReleaseWorkflow, _NOOP_STEPS
from ._common import __version__, _fatal, _read_matrix
from .workflow import _load_yaml


def _compute_skipped(args: argparse.Namespace) -> set[str]:
    """Merge --skip and --skip-to into a single set of job names to skip."""
    skipped: set[str] = set(args.skip or [])
    if args.skip_to:
        idx = JOB_ORDER.index(args.skip_to)
        skipped |= set(JOB_ORDER[:idx])
    return skipped


def _validate_skip_reuse(
    skipped: set[str],
    reuse_run: str | None,
    reuse_release: bool,
) -> None:
    """Validate skip/reuse flag combinations."""
    build_skipped = "build" in skipped
    has_reuse = reuse_run is not None or reuse_release

    if build_skipped and not has_reuse:
        _fatal(
            "Build is being skipped but no artifact source specified.\n"
            "  Add --reuse-run RUN_ID or --reuse-release."
        )
    if has_reuse and not build_skipped:
        _fatal(
            "--reuse-run / --reuse-release requires build to be skipped.\n"
            "  Add --skip build or --skip-to <job-after-build>."
        )
    if reuse_run and reuse_release:
        _fatal("--reuse-run and --reuse-release are mutually exclusive.")


def cmd_release(args: argparse.Namespace) -> None:
    """Generate a release plan and optionally dispatch the executor workflow."""
    # Late import to allow patching via ``uv_release_monorepo.cli.build_plan``.
    import uv_release_monorepo.cli as _cli

    root = Path.cwd()
    workflow_path = root / args.workflow_dir / "release.yml"
    if not workflow_path.exists():
        _fatal("No release workflow found. Run `uvr init` first.")

    # Compute and validate skip/reuse
    skipped = _compute_skipped(args)
    reuse_run: str | None = getattr(args, "reuse_run", None)
    reuse_release: bool = getattr(args, "reuse_release", False)
    _validate_skip_reuse(skipped, reuse_run, reuse_release)

    # Read stored matrix from pyproject.toml
    package_runners = _read_matrix(root)

    # Build the plan locally (runs discovery + change detection + pin updates)
    plan, pin_updates = _cli.build_plan(
        rebuild_all=args.rebuild_all,
        matrix=package_runners,
        uvr_version=__version__,
        python_version=args.python_version,
    )

    if pin_updates:
        print()
        print("Dep pins updated -- commit these changes before releasing:")
        for name in pin_updates:
            print(f"  git add {plan.changed[name].path}/pyproject.toml")
        print("  git commit -m 'chore: update dep pins'")
        print("  git push")
        print("  uvr release")
        return

    if not plan.changed:
        print("Nothing changed since last release. Use --rebuild-all to rebuild all.")
        return

    # Auto-skip hook jobs that only have the default no-op step
    _HOOK_PHASES = ["pre-build", "post-build", "pre-release", "post-release"]
    workflow_doc = _load_yaml(root / args.workflow_dir / "release.yml")
    model = ReleaseWorkflow.model_validate(workflow_doc)
    jobs_dict = model.model_dump(by_alias=True, exclude_none=True).get("jobs", {})
    for phase in _HOOK_PHASES:
        job = jobs_dict.get(phase, {})
        if job.get("steps") == _NOOP_STEPS:
            skipped.add(phase)

    # Set skip/reuse fields on the plan
    if skipped:
        plan.skip = sorted(skipped)
    if reuse_run:
        plan.reuse_run_id = reuse_run

    # Don't pin to a .dev version -- it won't exist on PyPI.
    if ".dev" in plan.uvr_version:
        plan.uvr_version = ""

    # Print the plan
    print(json.dumps(plan.model_dump(), indent=2))

    # Prompt for confirmation before dispatching (skip with --yes)
    if not args.yes:
        try:
            answer = input("\nDispatch release? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer != "y":
            return

    # Dispatch via gh
    import subprocess
    import time

    plan_json = plan.model_dump_json()
    cmd = [
        "gh",
        "workflow",
        "run",
        "release.yml",
        "-f",
        f"plan={plan_json}",
    ]
    print(f"Triggering release for: {', '.join(sorted(plan.changed))}")
    if skipped:
        print(f"Skipping: {', '.join(sorted(skipped))}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        _fatal("Failed to trigger workflow")

    # Wait for the run to be created and fetch its URL
    print("Waiting for workflow run...")
    time.sleep(2)

    result = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--workflow=release.yml",
            "--limit=1",
            "--json=url,status",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout:
        try:
            runs = json.loads(result.stdout)
            if runs:
                url = runs[0].get("url", "")
                status = runs[0].get("status", "")
                print(f"Status: {status}")
                print(f"Watch:  {url}")
        except json.JSONDecodeError:
            pass
