"""Helpers for script-based GitHub Actions workflow steps."""

from __future__ import annotations

import json
import os
import sys

from lazy_wheels.pipeline import (
    build_packages,
    bump_versions,
    commit_bumps,
    detect_changes,
    discover_packages,
    fetch_unchanged_wheels,
    find_last_tags,
    find_next_release_tag,
    publish_release,
    tag_changed_packages,
)


def _write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a") as fh:
        fh.write(f"{name}={value}\n")


def plan() -> None:
    """Compute release plan and emit GitHub step outputs."""
    release = os.environ.get("INPUT_RELEASE") or find_next_release_tag()
    force_all = os.environ.get("FORCE_ALL", "").lower() == "true"
    packages = discover_packages()
    last_tags = find_last_tags(packages)
    changed = sorted(detect_changes(packages, last_tags, force_all))
    if not changed:
        raise SystemExit("Nothing changed since last release.")
    unchanged = sorted(name for name in packages if name not in changed)

    _write_output("changed", json.dumps(changed))
    _write_output("unchanged", json.dumps(unchanged))
    _write_output("last_tags", json.dumps(last_tags))
    _write_output("release", release)


def build_one() -> None:
    """Build a single package from matrix inputs if it's changed."""
    package = os.environ["PACKAGE"]
    changed = set(json.loads(os.environ["CHANGED"]))
    if package not in changed:
        return
    packages = discover_packages()
    build_packages({package: packages[package]})


def fetch_unchanged() -> None:
    """Fetch unchanged package wheels based on serialized state."""
    packages = discover_packages()
    unchanged_names = json.loads(os.environ["UNCHANGED"])
    last_tags = json.loads(os.environ["LAST_TAGS"])
    unchanged = {name: packages[name] for name in unchanged_names}
    fetch_unchanged_wheels(unchanged, last_tags)


def finalize_release() -> None:
    """Tag, bump, commit, and publish using serialized state."""
    packages = discover_packages()
    changed_names = json.loads(os.environ["CHANGED"])
    unchanged_names = json.loads(os.environ["UNCHANGED"])
    changed = {name: packages[name] for name in changed_names}
    unchanged = {name: packages[name] for name in unchanged_names}
    tag_changed_packages(changed)
    bumped = bump_versions(changed, unchanged)
    commit_bumps(changed, bumped)
    publish_release(changed, unchanged, os.environ["RELEASE_TAG"])


def main(argv: list[str] | None = None) -> None:
    """Run a workflow step command."""
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        raise SystemExit("Usage: python -m lazy_wheels.workflow_steps <step>")

    command = args[0]
    if command == "plan":
        plan()
    elif command == "build-one":
        build_one()
    elif command == "fetch-unchanged":
        fetch_unchanged()
    elif command == "finalize-release":
        finalize_release()
    else:
        raise SystemExit(f"Unknown step: {command!r}")


if __name__ == "__main__":
    main()
