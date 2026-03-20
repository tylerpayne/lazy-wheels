"""Helpers for script-based GitHub Actions workflow steps."""

from __future__ import annotations

import argparse
import json
import sys

from .models import ReleasePlan
from .pipeline import (
    build_packages,
    bump_versions,
    collect_published_state,
    commit_bumps,
    detect_changes,
    discover_packages,
    fetch_unchanged_wheels,
    find_dev_baselines,
    find_release_tags,
    publish_release,
    run_release,
    tag_changed_packages,
    tag_dev_baselines,
)

# Increment when the JSON schema passed between workflow steps changes shape.
# Consumers check this to give a clear error instead of a cryptic failure.
SCHEMA_VERSION = 1


def run_pipeline(force_all: bool, push: bool = True, dry_run: bool = False) -> None:
    """Run the full release pipeline."""
    run_release(force_all=force_all, push=push, dry_run=dry_run)


def execute_build(plan_json: str, package: str) -> None:
    """CI build step: build one package if it is in the plan's changed set."""
    plan = ReleasePlan.model_validate_json(plan_json)
    if package not in plan.changed:
        print(f"  {package} not in changed list, skipping")
        return
    build_packages({package: plan.changed[package]})


def execute_fetch_unchanged(plan_json: str) -> None:
    """CI step: download wheels for unchanged packages from their GitHub releases."""
    plan = ReleasePlan.model_validate_json(plan_json)
    fetch_unchanged_wheels(plan.unchanged, plan.release_tags)


def execute_publish_releases(plan_json: str) -> None:
    """CI step: create one GitHub release per changed package."""
    plan = ReleasePlan.model_validate_json(plan_json)
    publish_release(plan.changed, plan.release_tags)


def execute_finalize(plan_json: str) -> None:
    """CI step: tag packages, bump versions, commit, and tag dev baselines."""
    plan = ReleasePlan.model_validate_json(plan_json)
    published_state = collect_published_state(
        plan.changed, plan.unchanged, plan.release_tags
    )
    tag_changed_packages(plan.changed)
    bumped = bump_versions(published_state)
    commit_bumps(plan.changed, bumped)
    tag_dev_baselines(bumped)


def execute_release(plan_json: str) -> None:
    """Run all release steps in sequence (convenience wrapper for local use)."""
    execute_fetch_unchanged(plan_json)
    execute_publish_releases(plan_json)
    execute_finalize(plan_json)


def _parse_json(value: str, *, arg_name: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON for {arg_name}: {exc}") from exc


def _parse_package_list(value: str, *, arg_name: str) -> list[str]:
    data = _parse_json(value, arg_name=arg_name)
    if not isinstance(data, list):
        raise SystemExit(
            f"{arg_name}: expected JSON array, got {type(data).__name__}. "
            "Re-run `uvr init` to regenerate the workflow file."
        )
    return data


def _parse_release_tags(value: str, *, arg_name: str) -> dict[str, str | None]:
    data = _parse_json(value, arg_name=arg_name)
    if not isinstance(data, dict):
        raise SystemExit(
            f"{arg_name}: expected JSON object, got {type(data).__name__}. "
            "Re-run `uvr init` to regenerate the workflow file."
        )
    return data


def _write_output(output_path: str, name: str, value: str) -> None:
    with open(output_path, "a") as fh:
        fh.write(f"{name}={value}\n")


def discover(force_all: bool, github_output: str) -> None:
    """Compute release plan and emit GitHub step outputs."""
    packages = discover_packages()
    release_tags = find_release_tags(packages)
    dev_baselines = find_dev_baselines(packages)
    changed = sorted(detect_changes(packages, dev_baselines, force_all))
    if not changed:
        raise SystemExit("Nothing changed since last release.")
    unchanged = sorted(name for name in packages if name not in changed)

    _write_output(github_output, "schema_version", str(SCHEMA_VERSION))
    _write_output(github_output, "changed", json.dumps(changed))
    _write_output(github_output, "unchanged", json.dumps(unchanged))
    _write_output(github_output, "release_tags", json.dumps(release_tags))


def build(package: str, changed_json: str) -> None:
    """Build a single package from matrix inputs if it's changed."""
    changed = set(_parse_package_list(changed_json, arg_name="--changed"))
    if package not in changed:
        return
    packages = discover_packages()
    build_packages({package: packages[package]})


def release(
    changed_json: str,
    unchanged_json: str,
    release_tags_json: str,
) -> None:
    """Fetch unchanged wheels, then publish, tag, bump, and commit."""
    packages = discover_packages()
    changed_names = _parse_package_list(changed_json, arg_name="--changed")
    unchanged_names = _parse_package_list(unchanged_json, arg_name="--unchanged")
    release_tags = _parse_release_tags(release_tags_json, arg_name="--release-tags")

    changed = {name: packages[name] for name in changed_names}
    unchanged = {name: packages[name] for name in unchanged_names}
    published_state = collect_published_state(changed, unchanged, release_tags)
    fetch_unchanged_wheels(unchanged, release_tags)
    publish_release(changed, release_tags)
    tag_changed_packages(changed)
    bumped = bump_versions(published_state)
    commit_bumps(changed, bumped)
    tag_dev_baselines(bumped)


def main(argv: list[str] | None = None) -> None:
    """Run a workflow step command."""
    args = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="python -m uv_release_monorepo.workflow_steps"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover")
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
        "--release-tags",
        required=True,
        help="JSON object mapping package name to its previous release tag.",
    )

    execute_build_parser = subparsers.add_parser("execute-build")
    execute_build_parser.add_argument(
        "--plan", required=True, help="Release plan JSON."
    )
    execute_build_parser.add_argument(
        "--package", required=True, help="Package name to build."
    )

    execute_release_parser = subparsers.add_parser("execute-release")
    execute_release_parser.add_argument(
        "--plan", required=True, help="Release plan JSON."
    )

    fetch_unchanged_parser = subparsers.add_parser("fetch-unchanged")
    fetch_unchanged_parser.add_argument(
        "--plan", required=True, help="Release plan JSON."
    )

    publish_releases_parser = subparsers.add_parser("publish-releases")
    publish_releases_parser.add_argument(
        "--plan", required=True, help="Release plan JSON."
    )

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--plan", required=True, help="Release plan JSON.")

    parsed = parser.parse_args(args)
    if parsed.command == "discover":
        discover(parsed.force_all, parsed.github_output)
    elif parsed.command == "build":
        build(parsed.package, parsed.changed)
    elif parsed.command == "release":
        release(parsed.changed, parsed.unchanged, parsed.release_tags)
    elif parsed.command == "execute-build":
        execute_build(parsed.plan, parsed.package)
    elif parsed.command == "execute-release":
        execute_release(parsed.plan)
    elif parsed.command == "fetch-unchanged":
        execute_fetch_unchanged(parsed.plan)
    elif parsed.command == "publish-releases":
        execute_publish_releases(parsed.plan)
    elif parsed.command == "finalize":
        execute_finalize(parsed.plan)


if __name__ == "__main__":
    main()
