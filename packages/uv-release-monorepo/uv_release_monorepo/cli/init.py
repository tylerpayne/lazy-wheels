"""The ``uvr init`` and ``uvr validate`` commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..models import ReleaseWorkflow
from ..toml import load_pyproject
from ._common import _fatal
from ._yaml import _load_yaml, _write_yaml


def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold the GitHub Actions workflow into your repo."""
    root = Path.cwd()

    # Sanity checks
    if not (root / ".git").exists():
        _fatal("Not a git repository. Run from the repo root.")

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        _fatal("No pyproject.toml found in current directory.")

    doc = load_pyproject(pyproject)
    members = doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members")
    if not members:
        _fatal(
            "No [tool.uv.workspace] members defined in pyproject.toml.\n"
            "uvr requires a uv workspace. Example:\n\n"
            "  [tool.uv.workspace]\n"
            '  members = ["packages/*"]'
        )

    # Write workflow
    dest_dir = root / args.workflow_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "release.yml"

    force = getattr(args, "force", False)
    if dest.exists() and not force:
        _fatal(
            f"{dest.relative_to(root)} already exists.\n"
            "  Use --force to overwrite, or `uvr validate` to check the existing file."
        )

    _write_yaml(dest, ReleaseWorkflow().model_dump(by_alias=True, exclude_none=True))

    print(f"\u2713 Wrote workflow to {dest.relative_to(root)}")
    print()
    print("Next steps:")
    print("  1. Edit the workflow to add your hook steps")
    print("  2. Run `uvr validate` to check your changes")
    print("  3. Commit and push the workflow file")
    print("  4. Trigger a release:")
    print("       uvr release")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate an existing release.yml against the ReleaseWorkflow model."""
    root = Path.cwd()
    workflow_dir = getattr(args, "workflow_dir", ".github/workflows")
    dest = root / workflow_dir / "release.yml"

    if not dest.exists():
        _fatal(f"No workflow found at {dest.relative_to(root)}. Run `uvr init` first.")

    import warnings

    from pydantic import ValidationError

    existing = _load_yaml(dest)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            ReleaseWorkflow.model_validate(existing)
        except ValidationError as e:
            print(f"\u2717 {dest.relative_to(root)} is invalid:\n{e}")
            raise SystemExit(1) from None

    if caught:
        print(f"\u26a0 {dest.relative_to(root)} has warnings:")
        for w in caught:
            print(f"  {w.message}")
    else:
        print(f"\u2713 {dest.relative_to(root)} is valid.")
