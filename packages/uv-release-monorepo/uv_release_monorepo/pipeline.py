"""Release pipeline: discover → diff → build → publish → tag → bump.

This module orchestrates the uv-release-monorepo release process:
1. Discover all packages in the workspace
2. Detect which packages changed since last release
3. Fetch unchanged wheels from previous release (avoid rebuilding)
4. Build only the changed packages
5. Publish wheels to GitHub Releases
6. Tag released packages (only after successful publish)
7. Bump versions for next development cycle
8. Push tags and version bump commit back to main

The key optimization is that unchanged packages are not rebuilt - their
wheels are reused from the previous release. Tagging and bumping happen
only after a successful publish, so a failed release leaves no artifacts.
"""

from __future__ import annotations

import glob
import json
from collections.abc import Mapping
from pathlib import Path

from packaging.utils import canonicalize_name

from .deps import dep_canonical_name, rewrite_pyproject
from .graph import topo_sort
from .models import MatrixEntry, PackageInfo, PublishedPackage, ReleasePlan, VersionBump
from .shell import fatal, gh, git, run, step
from .toml import (
    get_all_dependency_strings,
    get_project_name,
    get_project_version,
    get_workspace_member_globs,
    load_pyproject,
)
from .versions import bump_patch


def discover_packages(root: Path | None = None) -> dict[str, PackageInfo]:
    """Scan the workspace and discover all packages.

    Reads [tool.uv.workspace].members from root pyproject.toml to find
    package directories, then extracts name, version, and internal deps
    from each package's pyproject.toml.

    Args:
        root: Workspace root directory. Defaults to the current working directory.

    Returns:
        Map of package name to PackageInfo.
    """
    step("Discovering workspace packages")

    root = root or Path.cwd()
    root_doc = load_pyproject(root / "pyproject.toml")
    member_globs = get_workspace_member_globs(root_doc)

    # Expand globs to find all package directories
    member_dirs: list[Path] = []
    for pattern in member_globs:
        for match in sorted(glob.glob(str(root / pattern))):
            p = Path(match)
            if (p / "pyproject.toml").exists():
                member_dirs.append(p)

    if not member_dirs:
        fatal(
            "No packages found matching workspace members. "
            "Run from repo root; check [tool.uv.workspace].members in pyproject.toml."
        )

    # First pass: collect basic info from each package
    packages: dict[str, PackageInfo] = {}
    raw_deps: dict[str, list[str]] = {}

    for d in member_dirs:
        doc = load_pyproject(d / "pyproject.toml")
        name = get_project_name(doc, d.name)
        packages[name] = PackageInfo(
            path=str(d.relative_to(root)),
            version=get_project_version(doc),
        )
        raw_deps[name] = get_all_dependency_strings(doc)

    # Second pass: identify which deps are internal (within workspace)
    workspace_names = set(packages.keys())
    for name, deps in raw_deps.items():
        seen: set[str] = set()
        for dep_str in deps:
            dep_name = dep_canonical_name(dep_str)
            # Only track internal deps, ignore external packages
            if dep_name in workspace_names and dep_name not in seen:
                packages[name].deps.append(dep_name)
                seen.add(dep_name)

    # Print discovered packages for user feedback
    for name, info in packages.items():
        deps = f" → [{', '.join(info.deps)}]" if info.deps else ""
        print(f"  {name} {info.version} ({info.path}){deps}")

    return packages


def find_release_tags(packages: dict[str, PackageInfo]) -> dict[str, str | None]:
    """Find the most recent release tag for each package.

    Tags follow the pattern {package-name}/v{version}. Dev baseline tags
    ({package-name}/v{version}-dev) are excluded.

    Args:
        packages: Map of package name → PackageInfo.

    Returns:
        Map of package name to its last release tag, or None if no tag exists.
    """
    step("Finding last release tags")

    release_tags: dict[str, str | None] = {}
    for name in packages:
        # Get tags matching this package's pattern, sorted by version
        tags = git("tag", "--list", f"{name}/v*", "--sort=-v:refname", check=False)
        # Find the first tag that is NOT a -dev baseline
        found = None
        for tag in tags.splitlines():
            if not tag.endswith("-dev"):
                found = tag
                break
        release_tags[name] = found
        print(f"  {name}: {found or '<none>'}")

    return release_tags


def find_dev_baselines(packages: dict[str, PackageInfo]) -> dict[str, str | None]:
    """Find the dev baseline tag for each package.

    After each release, a {package-name}/v{next_version}-dev tag is created
    on the version bump commit. This tag serves as the diff baseline for the
    next release — everything after it is "real work."

    Falls back to the release tag if no -dev tag exists (backward compat).

    Args:
        packages: Map of package name → PackageInfo.

    Returns:
        Map of package name to its dev baseline tag, or None if no tag exists.
    """
    step("Finding dev baselines")

    baselines: dict[str, str | None] = {}
    for name in packages:
        # First, look for -dev baseline tags
        dev_tags = git(
            "tag", "--list", f"{name}/v*-dev", "--sort=-v:refname", check=False
        )
        if dev_tags:
            baselines[name] = dev_tags.splitlines()[0]
        else:
            # Fall back to release tag (backward compat with repos that
            # don't have -dev tags yet)
            release_tags = git(
                "tag", "--list", f"{name}/v*", "--sort=-v:refname", check=False
            )
            baselines[name] = release_tags.splitlines()[0] if release_tags else None
        print(f"  {name}: {baselines[name] or '<none>'}")

    return baselines


def detect_changes(
    packages: dict[str, PackageInfo],
    dev_baselines: Mapping[str, str | None],
    force_all: bool,
) -> list[str]:
    """Determine which packages need to be rebuilt.

    A package is "dirty" and needs rebuilding if:
    1. force_all is True (rebuild everything)
    2. No previous baseline tag exists for the package (first release)
    3. Any file in the package directory changed since its dev baseline
    4. Root pyproject.toml or uv.lock changed since its dev baseline
    5. Any of its dependencies are dirty (transitive dirtiness)

    The dev baseline tag ({pkg}/v{version}-dev) is placed on the version
    bump commit after each release, so only real work after the bump
    shows up in the diff.

    Args:
        packages: Map of package name → PackageInfo.
        dev_baselines: Map of package name → dev baseline tag (or None).
        force_all: If True, mark all packages as dirty.

    Returns:
        List of changed package names.
    """
    step("Detecting changes")

    if force_all:
        dirty = set(packages.keys())
        print("  Force rebuild: all packages marked dirty")
    else:
        dirty: set[str] = set()
        # Check each package for direct changes since its dev baseline
        for name, info in packages.items():
            baseline = dev_baselines.get(name)
            if not baseline:
                # First release for this package
                dirty.add(name)
                print(f"  {name}: new package")
                continue

            # Get files changed since this package's dev baseline
            changed_files = set(
                git("diff", "--name-only", baseline, "HEAD").splitlines()
            )

            # Filter to files in this package's directory
            prefix = info.path.rstrip("/") + "/"
            pkg_changed_files = {f for f in changed_files if f.startswith(prefix)}

            if pkg_changed_files:
                dirty.add(name)
                print(f"  {name}: changed since {baseline}")

            # Root config changes affect this package
            elif changed_files & {"pyproject.toml", "uv.lock"}:
                dirty.add(name)
                print(f"  {name}: root config changed since {baseline}")

    # Build reverse dependency map
    reverse_deps: dict[str, list[str]] = {n: [] for n in packages}
    for name, info in packages.items():
        for dep in info.deps:
            reverse_deps[dep].append(name)

    # Propagate dirtiness to dependents using BFS
    queue = list(dirty)
    while queue:
        node = queue.pop(0)
        for dependent in reverse_deps[node]:
            if dependent not in dirty:
                print(f"  {dependent}: dirty (depends on {node})")
                dirty.add(dependent)
                queue.append(dependent)

    return list(dirty)


def get_existing_wheels() -> set[str]:
    """Fetch all wheel filenames from all GitHub releases.

    Queries GitHub releases to build a set of all wheel files that have
    already been published. Used to prevent duplicate version releases.

    Returns:
        Set of wheel filenames (e.g., {"pkg_a-1.0.0-py3-none-any.whl"}).
        Returns empty set if no releases exist or gh CLI fails.
    """
    output = gh("release", "list", "--json", "tagName", "--limit", "100", check=False)
    if not output:
        return set()

    try:
        releases = json.loads(output)
    except json.JSONDecodeError:
        return set()

    existing_wheels: set[str] = set()

    for release in releases:
        tag = release.get("tagName", "")
        if not tag:
            continue

        assets_output = gh("release", "view", tag, "--json", "assets", check=False)
        if assets_output:
            try:
                assets_data = json.loads(assets_output)
                for asset in assets_data.get("assets", []):
                    name = asset.get("name", "")
                    if name.endswith(".whl"):
                        existing_wheels.add(name)
            except json.JSONDecodeError:
                continue

    return existing_wheels


def check_for_existing_wheels(changed: dict[str, PackageInfo]) -> None:
    """Check if any package version already exists in GitHub releases.

    Prevents accidentally releasing the same version twice by comparing
    the versions of packages about to be built against wheels already
    published in GitHub releases.

    Args:
        changed: Map of changed package names to PackageInfo.

    Raises:
        SystemExit: If any version already exists in releases.
    """
    step("Checking for duplicate versions")

    existing_wheels = get_existing_wheels()
    if not existing_wheels:
        print("  No existing releases found")
        return

    duplicates: list[str] = []

    for pkg_name, info in changed.items():
        # Wheel names use underscores, not hyphens
        wheel_prefix = (
            f"{canonicalize_name(pkg_name).replace('-', '_')}-{info.version}-"
        )

        for wheel in existing_wheels:
            if wheel.startswith(wheel_prefix):
                duplicates.append(f"{pkg_name} {info.version} (found: {wheel})")
                break

    if duplicates:
        fatal(
            "The following package versions already exist in releases:\n"
            + "\n".join(f"  - {d}" for d in duplicates)
            + "\n\nBump the version in pyproject.toml before releasing."
        )

    print("  No duplicates found")


def fetch_unchanged_wheels(
    unchanged: dict[str, PackageInfo],
    release_tags: Mapping[str, str | None],
) -> None:
    """Download wheels for unchanged packages from their per-package GitHub releases.

    Each package has its own GitHub release tagged {package}/v{version}. This
    function downloads the wheel for each unchanged package directly from its
    release, avoiding a full scan of all releases.

    Args:
        unchanged: Map of unchanged package names to PackageInfo.
        release_tags: Map of package name to last release tag (e.g. "pkg/v1.2.3").
    """
    if not unchanged:
        return

    step("Fetching unchanged wheels from releases")

    for name in unchanged:
        tag = release_tags.get(name)
        if not tag:
            print(f"  Warning: no release tag for {name}, skipping")
            continue

        wheel_name = canonicalize_name(name).replace("-", "_")
        result = run(
            "gh",
            "release",
            "download",
            tag,
            "--pattern",
            f"{wheel_name}-*.whl",
            "--dir",
            "dist/",
            "--clobber",
            check=False,
        )
        if result.returncode != 0:
            print(f"  Warning: could not download wheel for {name} from {tag}")
            continue

        # Find what was downloaded and report it
        released_version = tag.split("/v")[-1] if "/v" in tag else ""
        found = list(Path("dist").glob(f"{wheel_name}-{released_version}-*.whl"))
        if found:
            print(f"  Reusing: {found[0].name}")
        else:
            print(f"  Warning: no wheel found for {name} after downloading {tag}")


def build_packages(changed: dict[str, PackageInfo]) -> None:
    """Build wheels for the specified packages using uv build.

    Packages are built in topological order so dependencies are built
    before the packages that depend on them.
    """
    step(f"Building {len(changed)} packages")

    # Build in dependency order
    build_order = topo_sort(changed)
    for pkg in build_order:
        info = changed[pkg]
        print(f"\n  {pkg} ({info.path})")
        result = run("uv", "build", info.path, "--out-dir", "dist/", check=False)
        if result.returncode != 0:
            fatal(f"Failed to build {pkg}. Check uv build output above for details.")


def tag_changed_packages(changed: dict[str, PackageInfo]) -> None:
    """Create per-package git tags with format {package-name}/v{version}.

    Args:
        changed: Map of changed package names to PackageInfo.
    """
    step("Creating package tags")

    for name, info in changed.items():
        tag = f"{name}/v{info.version}"
        git("tag", tag)
        print(f"  {tag}")


def tag_dev_baselines(bumped: dict[str, VersionBump]) -> None:
    """Create dev baseline tags for each bumped package.

    These tags mark the version bump commit as the diff baseline for the
    next release. Format: {package-name}/v{new_version}-dev.

    Args:
        bumped: Map of package names to VersionBump (old → new versions).
    """
    step("Creating dev baseline tags")

    for name, bump in bumped.items():
        tag = f"{name}/v{bump.new}-dev"
        git("tag", tag)
        print(f"  {tag}")


def collect_published_state(
    changed: dict[str, PackageInfo],
    unchanged: dict[str, PackageInfo],
    release_tags: Mapping[str, str | None],
) -> dict[str, PublishedPackage]:
    """Record the published version of each package in this release cycle.

    Creates a snapshot of what version is now available on PyPI for every
    package — either just-built (changed) or fetched from a prior release
    (unchanged). This snapshot is used by bump_versions() to write correct
    minimum-version constraints into dependent packages' pyproject.toml files.

    Args:
        changed: Packages that were rebuilt in this cycle.
        unchanged: Packages whose previous wheel was reused.
        release_tags: Most recent release tag per package (e.g. "pkg/v0.1.5").
    """
    state: dict[str, PublishedPackage] = {}
    for name, info in changed.items():
        state[name] = PublishedPackage(
            info=info, published_version=info.version, changed=True
        )
    for name, info in unchanged.items():
        tag = release_tags.get(name)
        published = tag.split("/v")[-1] if tag and "/v" in tag else info.version
        state[name] = PublishedPackage(
            info=info, published_version=published, changed=False
        )
    return state


def bump_versions(
    published_state: dict[str, PublishedPackage],
) -> dict[str, VersionBump]:
    """Bump patch versions for changed packages, preparing for next release.

    After releasing 1.2.3, bumps to 1.2.4 so the next release will have
    a higher version. Pins internal dep constraints to the just-published
    versions (not the bumped dev versions) so that published wheels remain
    installable even when only a subset of packages change.

    Args:
        published_state: Per-package published state from collect_published_state().
    """
    step("Bumping versions for next release")

    changed_pkgs = {name: pkg for name, pkg in published_state.items() if pkg.changed}
    bumped: dict[str, VersionBump] = {}
    for name, pkg in changed_pkgs.items():
        bumped[name] = VersionBump(
            old=pkg.info.version, new=bump_patch(pkg.info.version)
        )
        # Pin internal deps to the version that was actually published this cycle,
        # not the bumped dev version — so the wheel stays installable if only
        # some packages change in the next cycle.
        internal_dep_versions = {
            dep: published_state[dep].published_version
            for dep in pkg.info.deps
            if dep in published_state
        }
        rewrite_pyproject(
            Path(pkg.info.path) / "pyproject.toml",
            bumped[name].new,
            internal_dep_versions,
        )
        print(f"  {name}: {bumped[name].old} → {bumped[name].new}")

    return bumped


def commit_bumps(
    changed: dict[str, PackageInfo], bumped: dict[str, VersionBump]
) -> None:
    """Commit and push the version bump changes."""
    # Stage all modified pyproject.toml files
    for name in bumped:
        git("add", changed[name].path + "/pyproject.toml")

    # Check if there are actually changes to commit
    staged = git("diff", "--cached", "--name-only", check=False)
    if not staged:
        fatal(
            "No changes to commit. "
            "Verify pyproject.toml files were modified by bump_versions."
        )

    # Need to commit new uv.lock too
    run("uv", "sync", "--all-groups", "--all-extras")
    git("add", "uv.lock")

    # Create commit with summary of version bumps
    summary = "\n".join(f"  {n}: {b.old} → {b.new}" for n, b in bumped.items())
    git("commit", "-m", "chore: prepare next release", "-m", summary)
    print("  Committed")


def publish_release(
    changed: dict[str, PackageInfo],
    release_tags: Mapping[str, str | None],
) -> None:
    """Create one GitHub release per changed package with its wheels attached.

    Each package gets its own release tagged {package}/v{version}, containing
    only that package's wheel(s). Release notes include per-package commit log
    since the last release.

    Args:
        changed: Map of changed package names to PackageInfo.
        release_tags: Most recent release tag per package (for changelog baseline).
    """
    step("Creating GitHub releases")

    for name, info in changed.items():
        release_tag = f"{name}/v{info.version}"
        wheel_name = canonicalize_name(name).replace("-", "_")
        wheels = sorted(
            str(p) for p in Path("dist").glob(f"{wheel_name}-{info.version}-*.whl")
        )
        if not wheels:
            fatal(
                f"No wheels found for {name} {info.version} in dist/. "
                "Ensure build_packages ran successfully."
            )

        # Per-package release notes
        lines: list[str] = [f"**Released:** {name} {info.version}"]
        baseline = release_tags.get(name)
        if baseline:
            log = git(
                "log",
                "--oneline",
                f"{baseline}..HEAD",
                "--",
                info.path,
                check=False,
            )
            if log:
                lines += ["", "**Commits:**"]
                for entry in log.splitlines()[:10]:
                    lines.append(f"- {entry}")

        gh(
            "release",
            "create",
            release_tag,
            *wheels,
            "--title",
            f"{name} {info.version}",
            "--notes",
            "\n".join(lines),
        )
        print(f"  {release_tag} ({len(wheels)} wheels)")


def run_release(
    *,
    force_all: bool = False,
    push: bool = True,
    dry_run: bool = False,
) -> None:
    """Execute the full release pipeline.

    Args:
        force_all: If True, rebuild all packages regardless of changes.
        push: If True (default), push commits and tags at the end.
        dry_run: If True, print what would happen without making any changes.
    """
    Path("dist").mkdir(parents=True, exist_ok=True)

    # Phase 1: Discovery
    packages = discover_packages()
    release_tags = find_release_tags(packages)
    dev_baselines = find_dev_baselines(packages)
    changed_names = detect_changes(packages, dev_baselines, force_all)

    if not changed_names:
        fatal(
            "Nothing changed since last release. "
            "Use --force-all to rebuild all packages."
        )

    # Split packages into changed and unchanged dicts
    changed = {name: packages[name] for name in changed_names}
    unchanged = {name: info for name, info in packages.items() if name not in changed}

    if dry_run:
        step("Dry-run: plan summary (no changes made)")
        print(f"  Would build: {', '.join(sorted(changed)) or 'none'}")
        print(f"  Would reuse: {', '.join(sorted(unchanged)) or 'none'}")
        for name, info in changed.items():
            new_ver = bump_patch(info.version)
            print(f"  Would bump {name}: {info.version} → {new_ver}")
        return

    # Check for duplicate versions before any build work
    check_for_existing_wheels(changed)

    # Phase 2: Build
    fetch_unchanged_wheels(unchanged, release_tags)
    build_packages(changed)

    # Phase 3: Publish first, then tag/bump only on success
    published_state = collect_published_state(changed, unchanged, release_tags)
    publish_release(changed, release_tags)
    tag_changed_packages(changed)
    bumped = bump_versions(published_state)
    commit_bumps(changed, bumped)
    tag_dev_baselines(bumped)

    if push:
        step("Pushing commits and tags.")
        git("push")
        git("push", "--tags")

    print(f"\n{'=' * 60}\nDone!\n{'=' * 60}")


def build_plan(
    *,
    force_all: bool,
    matrix: dict[str, list[str]],
    uvr_version: str,
    python_version: str = "3.12",
) -> ReleasePlan:
    """Run discovery locally and return a ReleasePlan. Makes no git writes.

    Args:
        force_all: If True, mark all packages as changed.
        matrix: Stored per-package runner config from the workflow file.
        uvr_version: The uvr version to embed in the plan.

    Returns:
        A ReleasePlan ready for inspection or dispatch to the executor workflow.
    """
    packages = discover_packages()
    release_tags = find_release_tags(packages)
    dev_baselines = find_dev_baselines(packages)
    changed_names = detect_changes(packages, dev_baselines, force_all)

    changed = {name: packages[name] for name in changed_names}
    unchanged = {
        name: info for name, info in packages.items() if name not in changed_names
    }

    # Expand matrix — only changed packages need build runners
    matrix_entries: list[MatrixEntry] = []
    for name in sorted(changed_names):
        runners = matrix.get(name, ["ubuntu-latest"])
        for runner in runners:
            matrix_entries.append(MatrixEntry(package=name, runner=runner))

    return ReleasePlan(
        uvr_version=uvr_version,
        python_version=python_version,
        force_all=force_all,
        changed=changed,
        unchanged=unchanged,
        release_tags=release_tags,
        matrix=matrix_entries,
    )


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

    published_state = collect_published_state(
        plan.changed, plan.unchanged, plan.release_tags
    )
    publish_release(plan.changed, plan.release_tags)
    tag_changed_packages(plan.changed)
    bumped = bump_versions(published_state)
    commit_bumps(plan.changed, bumped)
    tag_dev_baselines(bumped)

    if push:
        step("Pushing commits and tags.")
        git("push")
        git("push", "--tags")

    print(f"\n{'=' * 60}\nDone!\n{'=' * 60}")
