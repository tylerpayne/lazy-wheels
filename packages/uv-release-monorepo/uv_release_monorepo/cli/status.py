"""The ``uvr status`` command."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from ._common import _discover_packages, _read_matrix


def _section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def cmd_status(args: argparse.Namespace) -> None:
    """Show the current workspace status: packages, runners, and what has changed."""
    from uv_release_monorepo.shared.changes import detect_changes
    from uv_release_monorepo.shared.discovery import (
        discover_packages,
        get_baseline_tags,
    )

    root = Path.cwd()
    dest = root / args.workflow_dir / "release.yml"

    if not dest.exists():
        print("No release workflow found. Run `uvr init` to create one.")
        return

    # Discover packages (lightweight, no git)
    packages = _discover_packages()
    if not packages:
        print("No packages found.")
        return

    # Runners
    package_runners = _read_matrix(root)
    if not package_runners:
        package_runners = {pkg: ["ubuntu-latest"] for pkg in packages}

    # Detect dirty packages (suppress pipeline output)
    direct_dirty: set[str] = set()
    transitive_dirty: set[str] = set()
    try:
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            pipeline_pkgs = discover_packages()
            baselines = get_baseline_tags(pipeline_pkgs)
            all_dirty = set(detect_changes(pipeline_pkgs, baselines, rebuild_all=False))
        finally:
            sys.stdout = old_stdout
        direct_dirty = all_dirty.copy()
        # Transitive: packages dirty only because a dep changed
        for name in all_dirty:
            info = pipeline_pkgs.get(name)
            if info and any(dep in all_dirty for dep in info.deps):
                if name not in direct_dirty - {
                    n
                    for n in all_dirty
                    if pipeline_pkgs.get(n)
                    and any(d in all_dirty for d in pipeline_pkgs[n].deps)
                }:
                    transitive_dirty.add(name)
    except (SystemExit, Exception):
        pass

    # -- Packages --
    _section("Packages")
    names = sorted(packages.keys())
    w = max(len(n) for n in names)
    for name in names:
        version, deps = packages[name]
        if name in direct_dirty:
            status = "changed  "
        elif name in transitive_dirty:
            status = "transitive"
        else:
            status = "clean     "
        dep_str = f"  deps: {', '.join(sorted(deps))}" if deps else ""
        print(f"  {status}  {name.ljust(w)}  {version}{dep_str}")

    # -- Runners --
    _section("Runners")
    for pkg in sorted(package_runners.keys()):
        runners = package_runners[pkg]
        if runners == ["ubuntu-latest"]:
            continue  # skip default
        print(f"  {pkg}  {', '.join(runners)}")
    if all(r == ["ubuntu-latest"] for r in package_runners.values()):
        print("  (all packages use ubuntu-latest)")

    # -- Workflow --
    _section("Workflow")
    print(f"  {dest.relative_to(root)}")
    try:
        from uv_release_monorepo.cli._yaml import _load_yaml
        from uv_release_monorepo.shared.models import ReleaseWorkflow

        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            doc = _load_yaml(dest)
            ReleaseWorkflow.model_validate(doc)

        if caught:
            for w_msg in caught:
                print(f"  warning: {w_msg.message}")
        else:
            print("  valid")
    except Exception as e:
        print(f"  invalid: {e}")
