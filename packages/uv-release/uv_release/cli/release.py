"""The ``uvr release`` command."""

from __future__ import annotations
from typing import Literal

import argparse
import json
import sys
from pathlib import Path

from pydantic import Field

from ._args import CommandArgs
from .display import print_plan_summary
from ..execute import execute_plan
from ..plan.planner import create_plan
from ..types import Plan, PlanParams


class ReleaseArgs(CommandArgs):
    """Typed arguments for ``uvr release``."""

    where: Literal["ci", "local"] = "ci"
    dry_run: bool = False
    plan: str | None = None
    rebuild_all: bool = False
    rebuild: list[str] | None = None
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
            "uvr-validate",
            "uvr-build",
            "uvr-release",
            "uvr-publish",
            "uvr-bump",
        ]
        if parsed.skip_to not in _JOB_ORDER:
            print(
                f"ERROR: Unknown job '{parsed.skip_to}' for --skip-to.",
                file=sys.stderr,
            )
            sys.exit(1)
        idx = _JOB_ORDER.index(parsed.skip_to)
        skipped |= {j for j in _JOB_ORDER[:idx] if j != "uvr-validate"}

    params = PlanParams(
        rebuild_all=parsed.rebuild_all,
        rebuild=frozenset(parsed.rebuild or []),
        dev_release=parsed.dev,
        dry_run=dry_run,
        push=not parsed.no_push,
        skip=frozenset(skipped),
        release_notes=user_notes or None,
        target=parsed.where,
        require_clean_worktree=not dry_run,
    )
    plan = create_plan(params)

    if not plan.releases:
        if parsed.json_output:
            print(plan.model_dump_json(indent=2))
        else:
            print(
                "Nothing changed since last release. Use --rebuild-all to rebuild all."
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
    """Serialize the plan and dispatch to GitHub Actions."""
    import subprocess

    plan_json = plan.model_dump_json()
    ref_result = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True
    )
    ref = ref_result.stdout.strip() if ref_result.returncode == 0 else "main"
    cmd = [
        "gh",
        "workflow",
        "run",
        "release.yml",
        "--ref",
        ref,
        "-f",
        f"plan={plan_json}",
    ]

    print(f"Dispatching release for: {', '.join(sorted(plan.releases))}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("ERROR: Failed to trigger workflow.", file=sys.stderr)
        sys.exit(1)

    print("Waiting for workflow run...")
    import time

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
