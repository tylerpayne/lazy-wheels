"""The ``uvr release`` command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field

from ._args import CommandArgs
from ._display import print_plan_summary
from ..commands import DispatchWorkflowCommand
from ..planner import compute_plan
from ..intents.release import ReleaseIntent
from ..execute import execute_job, execute_plan
from ..types import Job, Plan, PlanParams


class ReleaseArgs(CommandArgs):
    """Typed arguments for ``uvr release``."""

    where: Literal["ci", "local"] = "ci"
    dry_run: bool = False
    plan: str | None = None
    all_packages: bool = False
    packages: list[str] | None = None
    dev: bool = False
    yes: bool = False
    skip: list[str] | None = None
    skip_to: str | None = None
    reuse_run: str | None = None
    reuse_release: bool = False
    no_push: bool = False
    json_output: bool = Field(False, alias="json")
    release_notes: list[list[str]] | None = None


def cmd_release(args: argparse.Namespace) -> None:
    """Plan and execute a release (locally or via CI)."""
    parsed = ReleaseArgs.from_namespace(args)

    # --plan: execute a pre-computed plan (CI mode)
    if parsed.plan:
        plan = _load_plan(parsed.plan)
        execute_plan(plan)
        return

    user_notes = _parse_release_notes(parsed.release_notes)

    dry_run = parsed.dry_run or parsed.json_output

    # Compute skip set from --skip and --skip-to
    skipped = set(parsed.skip or [])
    if parsed.skip_to:
        _JOB_ORDER = [
            "validate",
            "build",
            "download",
            "release",
            "publish",
            "bump",
        ]
        if parsed.skip_to not in _JOB_ORDER:
            print(
                f"ERROR: Unknown job '{parsed.skip_to}' for --skip-to.",
                file=sys.stderr,
            )
            sys.exit(1)
        idx = _JOB_ORDER.index(parsed.skip_to)
        skipped |= {j for j in _JOB_ORDER[:idx] if j != "validate"}

    params = PlanParams(
        all_packages=parsed.all_packages,
        packages=frozenset(parsed.packages or []),
    )
    intent = ReleaseIntent(
        dev_release=parsed.dev,
        skip=frozenset(skipped),
        release_notes=user_notes or {},
        target=parsed.where,
        reuse_run=parsed.reuse_run or "",
        reuse_release=parsed.reuse_release,
    )

    try:
        plan = compute_plan(intent, params=params)
    except ValueError as exc:
        if not dry_run:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        # Dry run tolerates guard failures
        plan = Plan()

    if not plan.jobs:
        if parsed.json_output:
            print(plan.model_dump_json(indent=2))
        else:
            print(
                "Nothing changed since last release. Use --all-packages to include all."
            )
        return

    # --json: emit plan JSON and exit
    if parsed.json_output:
        print(plan.model_dump_json(indent=2))
        return

    # Print human-readable summary
    print()
    print_plan_summary(plan)

    # --dry-run: stop after display
    if parsed.dry_run:
        return

    # Confirmation prompt (unless --yes)
    if not parsed.yes:
        print()
        try:
            answer = input("Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer != "y":
            return

    if parsed.where == "local":
        execute_plan(plan)
    else:
        _dispatch_to_ci(plan)


def _load_plan(source: str) -> Plan:
    """Load a Plan from a JSON string, @file reference, or stdin."""
    import os

    if source.startswith("@"):
        text = Path(source[1:]).read_text()
    elif source == "-":
        text = sys.stdin.read()
    else:
        text = source

    if not text:
        text = os.environ.get("UVR_PLAN", "")
    if not text:
        print("ERROR: No plan provided.", file=sys.stderr)
        sys.exit(1)
    return Plan.model_validate_json(text)


def _parse_release_notes(raw: list[list[str]] | None) -> dict[str, str]:
    """Convert --release-notes PKG NOTES pairs into a dict."""
    if not raw:
        return {}
    result: dict[str, str] = {}
    for pkg_name, notes_value in raw:
        if notes_value.startswith("@"):
            notes_path = Path(notes_value[1:])
            result[pkg_name] = notes_path.read_text()
        else:
            result[pkg_name] = notes_value
    return result


def _dispatch_to_ci(plan: Plan) -> None:
    """Serialize the plan and dispatch via the command framework."""
    print("Dispatching release...")
    dispatch_cmd = DispatchWorkflowCommand(
        label="Dispatch release to CI",
        plan_json=plan.model_dump_json(),
    )
    dispatch_job = Job(name="dispatch", commands=[dispatch_cmd])
    execute_job(dispatch_job, hooks=None)

    _poll_workflow_run()


def _poll_workflow_run() -> None:
    """Poll GitHub Actions for the latest workflow run status."""
    import subprocess
    import time

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
        except json.JSONDecodeError as exc:
            print(f"WARNING: Could not parse run status: {exc}", file=sys.stderr)
