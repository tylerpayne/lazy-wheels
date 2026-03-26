"""Execution: run the full release pipeline or execute a plan."""

from __future__ import annotations

from pathlib import Path


from ..deps import rewrite_pyproject
from ..models import PackageInfo, ReleasePlan
from ..versions import bump_patch, make_dev, strip_dev
from .build import build_packages, fetch_unchanged_wheels
from .bumps import bump_versions, collect_published_state, commit_bumps
from .changes import check_for_existing_wheels, detect_changes
from .discovery import discover_packages, find_release_tags, get_baseline_tags
from .plan import apply_bumps
from .publish import publish_release
from .tags import tag_baselines, tag_changed_packages
from ..shell import fatal, git, step


# TODO: What is this method? It runs in CI, right? Is it the build step? The publish step? Feels like maybe we can remove this method?
def run_release(
    *,
    rebuild_all: bool = False,
    push: bool = True,
    dry_run: bool = False,
) -> None:
    """Execute the full release pipeline.

    Args:
        rebuild_all: If True, rebuild all packages regardless of changes.
        push: If True (default), push commits and tags at the end.
        dry_run: If True, print what would happen without making any changes.
    """
    Path("dist").mkdir(parents=True, exist_ok=True)

    # Phase 1: Discovery
    packages = discover_packages()
    release_tags = find_release_tags(packages)
    baselines = get_baseline_tags(packages)
    changed_names = detect_changes(packages, baselines, rebuild_all)

    if not changed_names:
        fatal(
            "Nothing changed since last release. "
            "Use --rebuild-all to rebuild all packages."
        )

    # Split packages into changed and unchanged dicts
    changed = {name: packages[name] for name in changed_names}
    unchanged = {name: info for name, info in packages.items() if name not in changed}

    if dry_run:
        step("Dry-run: plan summary (no changes made)")
        print(f"  Would build: {', '.join(sorted(changed)) or 'none'}")
        print(f"  Would reuse: {', '.join(sorted(unchanged)) or 'none'}")
        for name, info in changed.items():
            release_ver = strip_dev(info.version)
            new_ver = bump_patch(info.version)
            print(
                f"  Would release {name} {release_ver}, then bump to {make_dev(new_ver)}"
            )
        return

    # Check for duplicate versions before any build work
    # Strip .dev for version comparison since that's the release version
    release_changed = {
        name: PackageInfo(
            # Why strip dev?
            path=info.path,
            version=strip_dev(info.version),
            deps=info.deps,
        )
        for name, info in changed.items()
    }
    check_for_existing_wheels(release_changed)

    # Strip .dev from pyproject.toml before building so wheels get clean versions
    for name, info in changed.items():
        release_ver = strip_dev(info.version)
        if release_ver != info.version:
            rewrite_pyproject(Path(info.path) / "pyproject.toml", release_ver, {})

    # Phase 2: Build
    fetch_unchanged_wheels(unchanged, release_tags)
    build_packages(release_changed)

    # Phase 3: Publish first, then tag/bump only on success
    published_state = collect_published_state(release_changed, unchanged, release_tags)
    publish_release(release_changed, release_tags)
    tag_changed_packages(release_changed)
    bumped = bump_versions(published_state)
    commit_bumps(release_changed, bumped)
    tag_baselines(bumped)

    if push:
        step("Pushing commits and tags.")
        git("push")
        git("push", "--tags")

    print(f"\n{'=' * 60}\nDone!\n{'=' * 60}")


def execute_plan(plan: ReleasePlan, *, push: bool = True) -> None:
    """Execute a ReleasePlan: build, publish, tag, bump, commit, push.

    Intended for local execution via `uvr run --plan`. The executor workflow
    uses execute_build / execute_release (in workflow_steps.py) instead, with
    the push step handled by the workflow YAML directly.

    Args:
        plan: The release plan to execute.
        push: If True (default), push commits and tags at the end.
    """
    Path("dist").mkdir(parents=True, exist_ok=True)

    check_for_existing_wheels(plan.changed)
    fetch_unchanged_wheels(plan.unchanged, plan.release_tags)
    build_packages(plan.changed)

    publish_release(plan.changed, plan.release_tags)
    tag_changed_packages(plan.changed)
    bumped = apply_bumps(plan)
    commit_bumps(plan.changed, bumped)
    tag_baselines(bumped)

    if push:
        step("Pushing commits and tags.")
        git("push")
        git("push", "--tags")

    print(f"\n{'=' * 60}\nDone!\n{'=' * 60}")
