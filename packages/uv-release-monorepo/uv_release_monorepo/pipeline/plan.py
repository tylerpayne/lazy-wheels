"""Planning: build release plans, write dep pins, apply bumps."""

from __future__ import annotations

import subprocess
from pathlib import Path

from packaging.utils import canonicalize_name


from ..deps import rewrite_pyproject, update_dep_pins
from ..models import (
    BumpPlan,
    MatrixEntry,
    PackageInfo,
    PublishEntry,
    ReleasePlan,
    VersionBump,
)
from ..toml import get_uvr_config, load_pyproject
from ..versions import bump_patch, make_dev, strip_dev
from .changes import detect_changes
from .discovery import discover_packages, find_release_tags, get_baseline_tags
from .publish import generate_release_notes
from ..shell import step


def build_plan(
    *,
    rebuild_all: bool,
    matrix: dict[str, list[str]],
    uvr_version: str,
    python_version: str = "3.12",
    # It's just a plan, what is a dry_run?
    dry_run: bool = False,
) -> tuple[ReleasePlan, list[tuple[str, list[tuple[str, str]]]]]:
    """Run discovery locally and return a ReleasePlan and pin change details.

    Applies internal dep pin updates to local pyproject.toml files so the
    correct constraints are baked into the released wheels. The caller should
    commit any pin changes before dispatching to CI.

    Args:
        rebuild_all: If True, mark all packages as changed.
        matrix: Stored per-package runner config from the workflow file.
        uvr_version: The uvr version to embed in the plan.
        dry_run: If True, detect pin updates but do not write them to disk.

    Returns:
        (plan, pin_updates) where pin_updates is a list of package names whose
        pyproject.toml was modified (or would be modified in dry_run mode).
        Empty list means no pin changes were needed.
    """
    packages = discover_packages()
    release_tags = find_release_tags(packages)
    baselines = get_baseline_tags(packages)
    changed_names = detect_changes(packages, baselines, rebuild_all)

    changed = {name: packages[name] for name in changed_names}
    unchanged = {
        name: info for name, info in packages.items() if name not in changed_names
    }

    # Strip .dev suffixes -- the plan stores clean release versions.
    for name, info in changed.items():
        changed[name] = PackageInfo(
            path=info.path, version=strip_dev(info.version), deps=info.deps
        )

    # Compute published versions for internal dep pinning:
    # changed packages publish at their current version; unchanged at their last tag.
    published_versions: dict[str, str] = {}
    for name in changed_names:
        published_versions[name] = changed[name].version
    for name, info in packages.items():
        if name not in changed_names:
            tag = release_tags.get(name)
            published_versions[name] = (
                tag.split("/v")[-1] if tag and "/v" in tag else info.version
            )

    # Check dep pins without writing -- caller is responsible for writing.
    pin_changes: list[tuple[str, list[tuple[str, str]]]] = []
    for name in changed_names:
        info = packages[name]
        dep_versions = {
            dep: published_versions[dep]
            for dep in info.deps
            if dep in published_versions
        }
        changes = update_dep_pins(
            Path(info.path) / "pyproject.toml", dep_versions, write=False
        )
        if changes:
            pin_changes.append((name, changes))

    # Pre-compute version bumps. Dep pins are already applied locally above.
    bumps: dict[str, BumpPlan] = {}
    for name in changed_names:
        bumps[name] = BumpPlan(new_version=bump_patch(changed[name].version))

    # Expand matrix -- only changed packages need build runners
    matrix_entries: list[MatrixEntry] = []
    for name in sorted(changed_names):
        info = changed[name]
        runners = matrix.get(name, ["ubuntu-latest"])
        for runner in runners:
            matrix_entries.append(
                MatrixEntry(
                    package=name,
                    runner=runner,
                    path=info.path,
                    version=info.version,
                )
            )

    # Build publish matrix -- one entry per changed package with precomputed notes
    root_doc = load_pyproject(Path.cwd() / "pyproject.toml")
    latest_pkg = get_uvr_config(root_doc).get("latest", "")
    publish_entries: list[PublishEntry] = []
    for name in sorted(changed_names):
        info = changed[name]
        baseline = release_tags.get(name)
        publish_entries.append(
            PublishEntry(
                package=name,
                version=info.version,
                tag=f"{name}/v{info.version}",
                title=f"{name} {info.version}",
                body=generate_release_notes(name, info, baseline),
                make_latest=name == latest_pkg,
                dist_name=canonicalize_name(name).replace("-", "_"),
            )
        )

    unique_runners = sorted(set(entry.runner for entry in matrix_entries))

    plan = ReleasePlan(
        uvr_version=uvr_version,
        python_version=python_version,
        rebuild_all=rebuild_all,
        changed=changed,
        unchanged=unchanged,
        release_tags=release_tags,
        matrix=matrix_entries,
        runners=unique_runners,
        bumps=bumps,
        publish_matrix=publish_entries,
        ci_publish=True,
    )
    return plan, pin_changes


# TODO: Use a structured response, not nested tuples
def write_dep_pins(plan: ReleasePlan) -> list[tuple[str, list[tuple[str, str]]]]:
    """Write pending dep pin updates via ``uv add --package PKG --frozen DEP>=VER``.

    Returns list of (package_name, [(old_spec, new_spec), ...]) for each
    package whose dependencies were updated.
    """
    # Compute published versions from the plan
    published_versions: dict[str, str] = {}
    for name, info in plan.changed.items():
        published_versions[name] = info.version
    for name in plan.unchanged:
        tag = plan.release_tags.get(name)
        published_versions[name] = (
            tag.split("/v")[-1] if tag and "/v" in tag else plan.unchanged[name].version
        )

    # Detect what needs updating (dry run)
    result: list[tuple[str, list[tuple[str, str]]]] = []
    for name, info in plan.changed.items():
        dep_versions = {
            dep: published_versions[dep]
            for dep in info.deps
            if dep in published_versions
        }
        changes = update_dep_pins(
            Path(info.path) / "pyproject.toml", dep_versions, write=False
        )
        if changes:
            result.append((name, changes))

    # Apply via uv add
    for name, changes in result:
        for _old_spec, new_spec in changes:
            cmd = [
                "uv",
                "add",
                "--package",
                name,
                "--frozen",
                new_spec,
            ]
            subprocess.run(cmd, check=True)

    return result


def apply_bumps(plan: ReleasePlan) -> dict[str, VersionBump]:
    """Apply pre-computed version bumps from the plan to pyproject.toml files.

    Writes ``.dev`` suffixed versions so pyproject.toml always reflects
    development state between releases. The plan stores clean release
    versions; CI never needs to derive them.
    """
    step("Bumping versions for next release")

    bumped: dict[str, VersionBump] = {}
    for name, bump_plan in plan.bumps.items():
        info = plan.changed[name]
        dev_version = make_dev(bump_plan.new_version)
        rewrite_pyproject(
            Path(info.path) / "pyproject.toml",
            dev_version,
            {},  # dep pins were committed locally before the release was triggered
        )
        bumped[name] = VersionBump(old=info.version, new=bump_plan.new_version)
        print(f"  {name}: {info.version} -> {dev_version}")

    return bumped
