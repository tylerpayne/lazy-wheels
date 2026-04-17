"""The ``uvr workflow validate`` command."""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

import tomlkit

from .._args import CommandArgs
from ...planner import compute_plan
from ...states.templates import load_workflow_template
from ...intents.validate_workflow import ValidateWorkflowIntent


class ValidateArgs(CommandArgs):
    """Typed arguments for ``uvr workflow validate``."""

    workflow_dir: str = ".github/workflows"
    diff: bool = False


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate an existing release.yml."""
    parsed = ValidateArgs.from_namespace(args)

    intent = ValidateWorkflowIntent(
        workflow_dir=parsed.workflow_dir,
        show_diff=parsed.diff,
    )

    try:
        plan = compute_plan(intent)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    errors = plan.validation_errors
    warnings = plan.validation_warnings
    has_diff = any("differs from bundled template" in w for w in warnings)

    if errors:
        print(f"FAIL: {len(errors)} error(s)")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    if warnings:
        print(f"OK: 0 errors, {len(warnings)} warning(s)")
        for w in warnings:
            print(f"  {w}")
    else:
        print("OK: 0 errors, 0 warnings")

    if has_diff:
        print("  Run `uvr workflow validate --diff` to view differences.")

    # Show stored version
    root = Path.cwd()
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        doc = tomlkit.loads(pyproject.read_text())
        stored_version = (
            doc.get("tool", {})
            .get("uvr", {})
            .get("config", {})
            .get("workflow_version", "")
        )
        if stored_version:
            print(f"  Workflow version: {stored_version}")

    if parsed.diff and has_diff:
        dest = root / parsed.workflow_dir / "release.yml"
        existing_text = dest.read_text()
        fresh_text = load_workflow_template()
        print()
        diff_lines = difflib.unified_diff(
            existing_text.splitlines(keepends=True),
            fresh_text.splitlines(keepends=True),
            fromfile=str(dest.relative_to(root)),
            tofile="template",
        )
        for line in diff_lines:
            print(line, end="")
