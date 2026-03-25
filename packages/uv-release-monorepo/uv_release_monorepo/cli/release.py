"""The ``uvr release`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ._common import __version__, _fatal, _read_matrix


def cmd_release(args: argparse.Namespace) -> None:
    """Generate a release plan and optionally dispatch the executor workflow."""
    # Late import to allow patching via ``uv_release_monorepo.cli.build_plan``.
    import uv_release_monorepo.cli as _cli

    root = Path.cwd()
    workflow_path = root / args.workflow_dir / "release.yml"
    if not workflow_path.exists():
        _fatal("No release workflow found. Run `uvr init` first.")

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
        print("Dep pins updated — commit these changes before releasing:")
        for name in pin_updates:
            print(f"  git add {plan.changed[name].path}/pyproject.toml")
        print("  git commit -m 'chore: update dep pins'")
        print("  git push")
        print("  uvr release")
        return

    if not plan.changed:
        print("Nothing changed since last release. Use --rebuild-all to rebuild all.")
        return

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
    # Don't pin to a .dev version — it won't exist on PyPI.
    # The workflow falls back to installing the latest release.
    uvr_ver = __version__ if ".dev" not in __version__ else ""
    cmd = [
        "gh",
        "workflow",
        "run",
        "release.yml",
        "-f",
        f"plan={plan_json}",
        "-f",
        f"uvr_version={uvr_ver}",
    ]
    print(f"Triggering release for: {', '.join(sorted(plan.changed))}")
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
