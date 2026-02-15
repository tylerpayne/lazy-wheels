"""Helpers for script-based GitHub Actions workflow steps."""

from __future__ import annotations

import argparse
import json
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
    run_release,
    tag_changed_packages,
)


def run_pipeline(release: str | None, force_all: bool) -> None:
    """Run the full release pipeline."""
    run_release(release=release, force_all=force_all)


def _parse_json(value: str, *, arg_name: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON for {arg_name}: {exc}") from exc


def _write_output(output_path: str, name: str, value: str) -> None:
    with open(output_path, "a") as fh:
        fh.write(f"{name}={value}\n")


def discover(release: str | None, force_all: bool, github_output: str) -> None:
    """Compute release plan and emit GitHub step outputs."""
    resolved_release = release or find_next_release_tag()
    packages = discover_packages()
    last_tags = find_last_tags(packages)
    changed = sorted(detect_changes(packages, last_tags, force_all))
    if not changed:
        raise SystemExit("Nothing changed since last release.")
    unchanged = sorted(name for name in packages if name not in changed)

    _write_output(github_output, "changed", json.dumps(changed))
    _write_output(github_output, "unchanged", json.dumps(unchanged))
    _write_output(github_output, "last_tags", json.dumps(last_tags))
    _write_output(github_output, "release", resolved_release)


def build(package: str, changed_json: str) -> None:
    """Build a single package from matrix inputs if it's changed."""
    changed = set(_parse_json(changed_json, arg_name="--changed"))
    if package not in changed:
        return
    packages = discover_packages()
    build_packages({package: packages[package]})


def release(
    changed_json: str,
    unchanged_json: str,
    last_tags_json: str,
    release_tag: str,
) -> None:
    """Fetch unchanged wheels, then tag, bump, commit, and publish."""
    packages = discover_packages()
    changed_names = _parse_json(changed_json, arg_name="--changed")
    unchanged_names = _parse_json(unchanged_json, arg_name="--unchanged")
    last_tags = _parse_json(last_tags_json, arg_name="--last-tags")

    changed = {name: packages[name] for name in changed_names}
    unchanged = {name: packages[name] for name in unchanged_names}
    fetch_unchanged_wheels(unchanged, last_tags)
    tag_changed_packages(changed)
    bumped = bump_versions(changed, unchanged)
    commit_bumps(changed, bumped)
    publish_release(changed, unchanged, release_tag)


def main(argv: list[str] | None = None) -> None:
    """Run a workflow step command."""
    args = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="python -m lazy_wheels.workflow_steps")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover")
    discover_parser.add_argument(
        "--release", default=None, help="Release tag to use; auto-generated if omitted."
    )
    discover_parser.add_argument(
        "--force-all",
        action="store_true",
        help="Force rebuild of all packages regardless of detected changes.",
    )
    discover_parser.add_argument(
        "--github-output", required=True, help="Path to GitHub step output file."
    )

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--package", required=True, help="Package name to build.")
    build_parser.add_argument(
        "--changed", required=True, help="JSON array of changed package names."
    )

    release_parser = subparsers.add_parser("release")
    release_parser.add_argument(
        "--changed", required=True, help="JSON array of changed package names."
    )
    release_parser.add_argument(
        "--unchanged", required=True, help="JSON array of unchanged package names."
    )
    release_parser.add_argument(
        "--last-tags",
        required=True,
        help="JSON object mapping package name to its previous release tag.",
    )
    release_parser.add_argument(
        "--release-tag", required=True, help="Release tag to publish."
    )

    parsed = parser.parse_args(args)
    if parsed.command == "discover":
        discover(parsed.release, parsed.force_all, parsed.github_output)
    elif parsed.command == "build":
        build(parsed.package, parsed.changed)
    elif parsed.command == "release":
        release(parsed.changed, parsed.unchanged, parsed.last_tags, parsed.release_tag)


if __name__ == "__main__":
    main()
