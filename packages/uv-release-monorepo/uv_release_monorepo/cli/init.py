"""The ``uvr init`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..toml import load_pyproject
from ._common import _WorkflowConfig, _empty_hooks, _fatal
from ._workflow_state import _get_workflow_state, _render_workflow


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

    # Render and write workflow template, preserving existing state
    force = getattr(args, "force", False)
    if dest.exists() and not force:
        hooks, config = _get_workflow_state(dest)
    else:
        hooks = _empty_hooks()
        config = _WorkflowConfig()
    _render_workflow(dest, hooks, config)

    print(f"\u2713 Wrote workflow to {dest.relative_to(root)}")
    print()
    print("Next steps:")
    print("  1. Commit and push the workflow file")
    print("  2. Trigger a release:")
    print("       uvr release")
    print("       uvr release --rebuild-all")
