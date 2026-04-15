"""The ``uvr workflow validate`` command."""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

import tomlkit

from .._args import CommandArgs
from .init import _load_template

_REQUIRED_JOBS = {"uvr-validate", "uvr-build", "uvr-release", "uvr-publish", "uvr-bump"}


class ValidateArgs(CommandArgs):
    """Typed arguments for ``uvr workflow validate``."""

    workflow_dir: str = ".github/workflows"
    diff: bool = False


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate an existing release.yml."""
    parsed = ValidateArgs.from_namespace(args)
    root = Path.cwd()
    dest = root / parsed.workflow_dir / "release.yml"

    if not dest.exists():
        print(
            f"ERROR: No workflow found at {dest.relative_to(root)}. "
            f"Run `uvr workflow init` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    existing_text = dest.read_text()

    # Parse YAML to check structure
    import yaml

    existing = yaml.safe_load(existing_text)

    warnings: list[str] = []
    errors: list[str] = []

    # Check required jobs
    if existing and "jobs" in existing:
        job_names = set(existing["jobs"].keys())
        missing = _REQUIRED_JOBS - job_names
        for job in sorted(missing):
            errors.append(f"Required job '{job}' is missing")
    elif existing:
        errors.append("No 'jobs' section found in release.yml")

    # Check stored version
    stored_version = ""
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        doc = tomlkit.loads(pyproject.read_text())
        stored_version = (
            doc.get("tool", {})
            .get("uvr", {})
            .get("config", {})
            .get("workflow_version", "")
        )

    # Compare against template
    fresh_text = _load_template()
    has_diff = fresh_text.rstrip() != existing_text.rstrip()
    if has_diff:
        warnings.append("Workflow differs from bundled template")

    # Print results
    rel = dest.relative_to(root)
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
    if stored_version:
        print(f"  Workflow version: {stored_version}")

    if parsed.diff and has_diff:
        print()
        diff_lines = difflib.unified_diff(
            existing_text.splitlines(keepends=True),
            fresh_text.splitlines(keepends=True),
            fromfile=str(rel),
            tofile="template",
        )
        for line in diff_lines:
            print(line, end="")
