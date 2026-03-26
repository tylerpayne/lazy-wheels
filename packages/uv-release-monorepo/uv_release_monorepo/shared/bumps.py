"""Version bumps: collect state, bump versions, commit changes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


from .models import PackageInfo, PublishedPackage, VersionBump
from .versions import bump_patch, make_dev, strip_dev, version_from_tag
from .deps import rewrite_pyproject
from .shell import fatal, git, run, step


def collect_published_state(
    changed: dict[str, PackageInfo],
    unchanged: dict[str, PackageInfo],
    release_tags: Mapping[str, str | None],
) -> dict[str, PublishedPackage]:
    """Record the published version of each package in this release cycle.

    Creates a snapshot of what version is now available on PyPI for every
    package -- either just-built (changed) or fetched from a prior release
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
        published = version_from_tag(tag) if tag and "/v" in tag else info.version
        state[name] = PublishedPackage(
            info=info, published_version=published, changed=False
        )
    return state


def bump_versions(
    published_state: dict[str, PublishedPackage],
) -> dict[str, VersionBump]:
    """Bump patch versions for changed packages, preparing for next release.

    After releasing 1.2.3, bumps to 1.2.4.dev so pyproject.toml always
    reflects development state. Pins internal dep constraints to the
    just-published versions (not the bumped dev versions) so that published
    wheels remain installable even when only a subset of packages change.

    Args:
        published_state: Per-package published state from collect_published_state().
    """
    step("Bumping versions for next release")

    changed_pkgs = {name: pkg for name, pkg in published_state.items() if pkg.changed}
    bumped: dict[str, VersionBump] = {}
    for name, pkg in changed_pkgs.items():
        new_version = bump_patch(pkg.info.version)
        # Why strip_dev? we can bump dev packages per the latest ADR, e.g. dev0 -> dev1
        bumped[name] = VersionBump(old=strip_dev(pkg.info.version), new=new_version)
        # Pin internal deps to the version that was actually published this cycle,
        # not the bumped dev version -- so the wheel stays installable if only
        # some packages change in the next cycle.
        internal_dep_versions = {
            dep: published_state[dep].published_version
            for dep in pkg.info.deps
            if dep in published_state
        }
        rewrite_pyproject(
            Path(pkg.info.path) / "pyproject.toml",
            make_dev(new_version),
            internal_dep_versions,
        )
        print(f"  {name}: {bumped[name].old} -> {make_dev(new_version)}")

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
    summary = "\n".join(f"  {n}: {b.old} -> {b.new}" for n, b in bumped.items())
    git("commit", "-m", "chore: prepare next release", "-m", summary)
    print("  Committed")
