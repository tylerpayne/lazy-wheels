"""The ``uvr bump`` command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ._common import _fatal
from ..shared.utils.dependencies import set_version
from ..shared.utils.versions import (
    bump_dev,
    bump_major,
    bump_minor,
    bump_patch,
    extract_pre_kind,
    get_base_version,
    make_dev,
    make_post,
    make_pre,
    strip_dev,
    validate_bump,
)

# Map CLI names (matching uv's --bump) to PEP 440 short pre-release kinds.
_PRE_KIND_MAP = {"alpha": "a", "beta": "b", "rc": "rc"}


def compute_bumped_version(
    current: str,
    *,
    bump_type: str,
) -> str:
    """Compute the new version after a bump.

    Args:
        current: Current version string from pyproject.toml.
        bump_type: One of "major", "minor", "patch", "alpha", "beta",
            "rc", "post", "dev".

    Returns:
        The bumped version string.
    """
    if bump_type == "major":
        return make_dev(bump_major(current))
    if bump_type == "minor":
        return make_dev(bump_minor(current))
    if bump_type == "patch":
        return make_dev(bump_patch(current))
    if bump_type in _PRE_KIND_MAP:
        return _bump_pre(current, _PRE_KIND_MAP[bump_type])
    if bump_type == "post":
        return _bump_post(current)
    if bump_type == "dev":
        return bump_dev(current)
    msg = f"Unknown bump type: {bump_type!r}"
    raise ValueError(msg)


def _bump_pre(current: str, kind: str) -> str:
    """Bump into a pre-release cycle: same kind → increment, new kind → start at 0."""
    import re

    without_dev = strip_dev(current)
    current_kind = extract_pre_kind(without_dev)
    if current_kind == kind:
        # Same kind → increment the pre number
        m = re.search(rf"{re.escape(kind)}(\d+)$", without_dev)
        n = int(m.group(1)) if m else -1
        return make_dev(make_pre(current, kind, n + 1))
    # New kind → start at 0
    return make_dev(make_pre(current, kind, 0))


def _bump_post(current: str) -> str:
    """Bump the post-release number."""
    import re

    without_dev = strip_dev(current)
    m = re.search(r"\.post(\d+)$", without_dev)
    n = int(m.group(1)) if m else -1
    base = get_base_version(current)
    return make_dev(make_post(base, n + 1))


def cmd_bump(args: argparse.Namespace) -> None:
    """Bump package versions in the workspace."""
    from ..shared.utils.packages import find_packages

    # Suppress discovery output
    import io

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        packages = find_packages()
    finally:
        sys.stdout = old_stdout

    # Resolve scope
    bump_all = getattr(args, "bump_all", False)
    changed = getattr(args, "changed", False)
    package_names: list[str] | None = getattr(args, "packages", None)

    if bump_all:
        targets = packages
    elif package_names:
        targets = {}
        for name in package_names:
            if name not in packages:
                _fatal(f"Unknown package: {name!r}")
            targets[name] = packages[name]
    elif changed:
        targets = _resolve_changed(packages)
    else:
        _fatal("Specify --all, --changed, or --package PKG.")

    if not targets:
        print("No packages to bump.")
        return

    # Determine bump type
    bump_type: str = getattr(args, "bump_type", None) or ""
    if not bump_type:
        _fatal(
            "Specify a bump type: --minor, --major, --alpha, --beta, --rc, --post, or --dev."
        )

    # Map pre-release names to internal representation for validation
    pre_kind = _PRE_KIND_MAP.get(bump_type, "")

    # Validate and compute new versions
    results: list[tuple[str, str, str]] = []
    for name in sorted(targets):
        info = targets[name]
        try:
            validate_bump(info.version, bump_type, pre_kind)
        except ValueError as exc:
            _fatal(f"{name}: {exc}")
        new_version = compute_bumped_version(info.version, bump_type=bump_type)
        results.append((name, info.version, new_version))

    # Write versions
    root = Path.cwd()
    for name, _old, new_version in results:
        pyproject = root / targets[name].path / "pyproject.toml"
        set_version(pyproject, new_version)

    # Sync lockfile
    subprocess.run(
        ["uv", "sync", "--all-groups", "--all-extras"],
        capture_output=True,
        check=False,
    )

    # Print summary
    nw = max(len(name) for name, _, _ in results)
    ow = max(len(old) for _, old, _ in results)
    for name, old, new in results:
        print(f"  {name.ljust(nw)}  {old.ljust(ow)}  ->  {new}")


def _resolve_changed(
    packages: dict,
) -> dict:
    """Resolve which packages have changes since their last release."""
    import io

    from ..shared.context import build_context
    from ..shared.utils.changes import detect_changes
    from ..shared.utils.versions import resolve_baseline

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        ctx = build_context()
        baselines: dict[str, str | None] = {}
        for name, info in ctx.packages.items():
            try:
                baselines[name] = resolve_baseline(
                    info.version, "final", name, ctx.repo
                )
            except ValueError:
                baselines[name] = None
        changed_names = detect_changes(ctx.packages, baselines, False, ctx=ctx)
    finally:
        sys.stdout = old_stdout

    return {name: packages[name] for name in changed_names if name in packages}
