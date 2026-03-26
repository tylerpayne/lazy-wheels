"""Helpers for script-based GitHub Actions workflow steps."""

from __future__ import annotations

import argparse
import sys

from .models import ReleasePlan
from .pipeline import (
    apply_bumps,
    build_packages,
    commit_bumps,
    fetch_unchanged_wheels,
    publish_release,
    run_release,
    tag_baselines,
    tag_changed_packages,
)
from .shell import git


def run_pipeline(rebuild_all: bool, push: bool = True, dry_run: bool = False) -> None:
    """Run the full release pipeline."""
    run_release(rebuild_all=rebuild_all, push=push, dry_run=dry_run)


def execute_prepare_release(plan_json: str, package: str) -> None:
    """CI step: strip .dev from a package's version before building."""
    from pathlib import Path

    from .deps import rewrite_pyproject
    from .versions import strip_dev

    plan = ReleasePlan.model_validate_json(plan_json)
    if package not in plan.changed:
        return
    info = plan.changed[package]
    # The plan stores the clean release version (already stripped).
    # Write it to pyproject.toml in case the checked-out file has .dev.
    rewrite_pyproject(
        Path(info.path) / "pyproject.toml",
        strip_dev(info.version),
        {},
    )


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
    """CI step: tag packages, apply pre-computed bumps, commit, tag dev baselines, push.

    Behavior is driven entirely by the plan:
    - ``ci_publish=True``: skip release tag creation (the publish action already
      created them), configure git identity, and push at the end.
    - ``ci_publish=False``: create release tags locally (default for local execution).
    """
    plan = ReleasePlan.model_validate_json(plan_json)
    if plan.ci_publish:
        git("config", "user.name", "github-actions[bot]")
        git("config", "user.email", "github-actions[bot]@users.noreply.github.com")
    if not plan.ci_publish:
        tag_changed_packages(plan.changed)
    bumped = apply_bumps(plan)
    commit_bumps(plan.changed, bumped)
    tag_baselines(bumped)
    if plan.ci_publish:
        git("push")
        git("push", "--tags")


def execute_build_all(plan_json: str, runner: str) -> None:
    """CI step: build all packages assigned to a runner in dependency order.

    For each package assigned to *runner*, this function:
    1. Collects its transitive internal deps (changed or unchanged).
    2. Fetches wheels for unchanged deps from their GitHub releases.
    3. Builds changed deps and assigned packages in topo order, passing
       ``--find-links dist/`` so ``uv build`` can resolve sibling wheels.
    4. Removes wheels for packages not assigned to this runner (they were
       only built as build-time dependencies).
    """
    from pathlib import Path

    from packaging.utils import canonicalize_name

    from .deps import rewrite_pyproject
    from .graph import topo_sort
    from .shell import run, step
    from .versions import strip_dev

    plan = ReleasePlan.model_validate_json(plan_json)

    # Which packages are assigned to this runner?
    assigned = {entry.package for entry in plan.matrix if entry.runner == runner}
    if not assigned:
        print(f"No packages assigned to runner {runner}")
        return

    # Collect transitive internal deps of the assigned packages.
    # A dep may be in plan.changed (must be built) or plan.unchanged (fetch wheel).
    all_packages = {**plan.changed, **plan.unchanged}

    def _collect_deps(names: set[str]) -> set[str]:
        visited: set[str] = set()
        queue = list(names)
        while queue:
            pkg = queue.pop()
            if pkg in visited:
                continue
            visited.add(pkg)
            if pkg in all_packages:
                for dep in all_packages[pkg].deps:
                    if dep in all_packages and dep not in visited:
                        queue.append(dep)
        return visited

    needed = _collect_deps(assigned)

    # Split into changed (build from source) and unchanged (fetch wheel).
    changed_to_build = {n: plan.changed[n] for n in needed if n in plan.changed}
    unchanged_deps = {n: plan.unchanged[n] for n in needed if n in plan.unchanged}

    # Fetch unchanged dep wheels into dist/ for --find-links.
    Path("dist").mkdir(parents=True, exist_ok=True)
    if unchanged_deps:
        fetch_unchanged_wheels(unchanged_deps, plan.release_tags)

    # Build changed packages in topo order.
    build_order = topo_sort(changed_to_build)
    step(f"Building {len(build_order)} packages for {runner}")

    for pkg in build_order:
        info = changed_to_build[pkg]
        # Prepare release version (strip .dev).
        rewrite_pyproject(
            Path(info.path) / "pyproject.toml",
            strip_dev(info.version),
            {},
        )
        print(f"\n  {pkg} ({info.path})")
        result = run(
            "uv",
            "build",
            info.path,
            "--out-dir",
            "dist/",
            "--find-links",
            "dist/",
            check=False,
        )
        if result.returncode != 0:
            from .pipeline import fatal

            fatal(f"Failed to build {pkg}. Check uv build output above for details.")

    # Remove wheels for packages not assigned to this runner.
    # They were only needed as build-time deps for --find-links.
    for pkg in list(changed_to_build) + list(unchanged_deps):
        if pkg not in assigned:
            dist_name = canonicalize_name(pkg).replace("-", "_")
            for whl in Path("dist").glob(f"{dist_name}-*.whl"):
                whl.unlink()


def execute_release(plan_json: str) -> None:
    """Run all release steps in sequence (convenience wrapper for local use)."""
    execute_fetch_unchanged(plan_json)
    execute_publish_releases(plan_json)
    execute_finalize(plan_json)


def main(argv: list[str] | None = None) -> None:
    """Run a workflow step command."""
    args = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="python -m uv_release_monorepo.workflow_steps"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    execute_build_parser = subparsers.add_parser("execute-build")
    execute_build_parser.add_argument(
        "--plan", required=True, help="Release plan JSON."
    )
    execute_build_parser.add_argument(
        "--package", required=True, help="Package name to build."
    )

    prepare_release_parser = subparsers.add_parser("prepare-release")
    prepare_release_parser.add_argument(
        "--plan", required=True, help="Release plan JSON."
    )
    prepare_release_parser.add_argument(
        "--package", required=True, help="Package name to prepare."
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

    build_all_parser = subparsers.add_parser("build-all")
    build_all_parser.add_argument("--plan", required=True, help="Release plan JSON.")
    build_all_parser.add_argument(
        "--runner", required=True, help="Runner name to build packages for."
    )

    parsed = parser.parse_args(args)
    if parsed.command == "execute-build":
        execute_build(parsed.plan, parsed.package)
    elif parsed.command == "prepare-release":
        execute_prepare_release(parsed.plan, parsed.package)
    elif parsed.command == "execute-release":
        execute_release(parsed.plan)
    elif parsed.command == "fetch-unchanged":
        execute_fetch_unchanged(parsed.plan)
    elif parsed.command == "publish-releases":
        execute_publish_releases(parsed.plan)
    elif parsed.command == "finalize":
        execute_finalize(parsed.plan)
    elif parsed.command == "build-all":
        execute_build_all(parsed.plan, parsed.runner)


if __name__ == "__main__":
    main()
