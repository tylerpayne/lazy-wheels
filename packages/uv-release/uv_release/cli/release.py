"""The ``uvr release`` command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field

from diny import provide

from ._args import CommandArgs
from ._display import print_plan_summary
from ..commands import DispatchWorkflowCommand
from ..planner import compute_plan
from ..intents.release import ReleaseIntent
from ..intents.release.params import ReleaseParams
from ..execute import execute_job, execute_plan
from ..types import Job, Plan, PlanParams, UserRecoverableError


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
        skipped |= _resolve_skip_to(
            parsed.skip_to,
            Path.cwd() / ".github/workflows/release.yml",
        )

    params = PlanParams(
        all_packages=parsed.all_packages,
        packages=frozenset(parsed.packages or []),
    )
    release_params = ReleaseParams(
        dev_release=parsed.dev,
        skip=frozenset(skipped),
        release_notes=user_notes or {},
        target=parsed.where,
        reuse_run=parsed.reuse_run or "",
        reuse_release=parsed.reuse_release,
    )
    intent = ReleaseIntent()

    try:
        with provide(params, release_params):
            plan = compute_plan(intent)
    except UserRecoverableError as exc:
        if dry_run:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        fix_job = Job(name="version-fix", commands=[exc.fix])
        execute_job(fix_job, hooks=None)
        with provide(params, release_params):
            plan = compute_plan(intent)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Merge skipped custom CI jobs into plan.skip so the workflow
    # ``if: !contains(...)`` condition can gate them.
    extra_skip = skipped - {j.name for j in plan.jobs} - {"validate"}
    if extra_skip and plan.jobs:
        plan = plan.model_copy(update={"skip": sorted(set(plan.skip) | extra_skip)})

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


_DEFAULT_JOB_ORDER = ["validate", "build", "release", "publish", "bump"]


def _read_workflow_job_dag(workflow_path: Path) -> dict[str, list[str]]:
    """Parse ``release.yml`` into a job dependency DAG.

    Returns a mapping of ``{job_name: [dependency_names]}`` derived from the
    ``needs:`` field of each job. Returns an empty dict when the file is
    missing or cannot be parsed.
    """
    if not workflow_path.exists():
        return {}
    try:
        import yaml

        content = yaml.safe_load(workflow_path.read_text())
    except Exception:
        return {}
    if not content or "jobs" not in content:
        return {}

    dag: dict[str, list[str]] = {}
    for name, config in content["jobs"].items():
        needs = config.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        dag[name] = needs
    return dag


def _resolve_skip_to(skip_to: str, workflow_path: Path) -> set[str]:
    """Resolve ``--skip-to`` into a set of job names to skip.

    Reads the workflow YAML, builds the job dependency DAG, and returns all
    ancestors of *skip_to* (except ``validate``). Falls back to the default
    linear order when no workflow file is available.
    """
    dag = _read_workflow_job_dag(workflow_path)

    if dag:
        if skip_to not in dag:
            print(
                f"ERROR: Unknown job '{skip_to}' for --skip-to.",
                file=sys.stderr,
            )
            sys.exit(1)
        from ..utils.graph import compute_ancestors

        return compute_ancestors(dag, skip_to) - {"validate"}

    # Fallback: no workflow file, use default linear order
    if skip_to not in _DEFAULT_JOB_ORDER:
        print(
            f"ERROR: Unknown job '{skip_to}' for --skip-to.",
            file=sys.stderr,
        )
        sys.exit(1)
    idx = _DEFAULT_JOB_ORDER.index(skip_to)
    return {j for j in _DEFAULT_JOB_ORDER[:idx] if j != "validate"}


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
