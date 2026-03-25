"""The ``uvr status`` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._common import (
    _discover_packages,
    _print_dependencies,
    _print_matrix_status,
    _read_matrix,
)


def cmd_status(args: argparse.Namespace) -> None:
    """Show the current workflow configuration."""
    from uv_release_monorepo.pipeline import (
        detect_changes,
        discover_packages,
        find_dev_baselines,
    )

    root = Path.cwd()
    dest = root / args.workflow_dir / "release.yml"

    if not dest.exists():
        print("No release workflow found.")
        print("Run `uvr init` to create one.")
        return

    package_runners = _read_matrix(root)
    packages = _discover_packages()
    if not package_runners:
        if packages:
            package_runners = {pkg: ["ubuntu-latest"] for pkg in packages}

    # Detect dirty packages using the pipeline's logic (suppress verbose output)
    import io

    direct_dirty: set[str] = set()
    transitive_dirty: set[str] = set()
    try:
        old_stdout = sys.stdout
        captured = io.StringIO()
        sys.stdout = captured
        try:
            pipeline_pkgs = discover_packages()
            dev_baselines = find_dev_baselines(pipeline_pkgs)
            all_dirty = set(
                detect_changes(pipeline_pkgs, dev_baselines, rebuild_all=False)
            )
        finally:
            sys.stdout = old_stdout

        # Parse captured output to distinguish direct vs transitive
        for line in captured.getvalue().splitlines():
            stripped = line.strip()
            if "dirty (depends on" in stripped:
                pkg_name = stripped.split(":")[0]
                transitive_dirty.add(pkg_name)
        direct_dirty = all_dirty - transitive_dirty
    except (SystemExit, Exception):
        pass  # Non-fatal — just skip dirty markers if detection fails

    _print_matrix_status(package_runners)
    _print_dependencies(
        packages, direct_dirty=direct_dirty, transitive_dirty=transitive_dirty
    )
