"""The ``uvr install`` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zipfile import ZipFile

from packaging.metadata import Metadata
from packaging.utils import canonicalize_name

from ..shared.utils.cli import (
    fatal,
    infer_gh_repo,
    parse_install_spec,
    resolve_gh_repo,
)
from ..shared.utils.tags import find_latest_remote_release_tag


def _read_internal_deps(wheel_path: Path, known_packages: set[str]) -> list[str]:
    """Extract internal workspace dependencies from a wheel's METADATA.

    Parses ``Requires-Dist`` entries and returns names that appear in
    *known_packages* (canonicalized).
    """
    try:
        with ZipFile(wheel_path) as zf:
            for name in zf.namelist():
                if name.endswith(".dist-info/METADATA"):
                    meta = Metadata.from_email(zf.read(name))
                    return [
                        canonicalize_name(req.name)
                        for req in (meta.requires_dist or [])
                        if canonicalize_name(req.name) in known_packages
                        and not (req.marker and "extra" in str(req.marker))
                    ]
    except Exception:
        pass
    return []


def _list_repo_packages(gh_repo: str) -> set[str]:
    """List all package names that have GitHub releases in a repo."""
    import json
    import subprocess

    result = subprocess.run(
        [
            "gh",
            "release",
            "list",
            "--repo",
            gh_repo,
            "--json",
            "tagName",
            "--limit",
            "200",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    try:
        releases = json.loads(result.stdout)
    except json.JSONDecodeError:
        return set()

    packages: set[str] = set()
    for r in releases:
        tag = r["tagName"]
        if "/v" in tag:
            pkg_name = tag.rsplit("/v", 1)[0]
            packages.add(canonicalize_name(pkg_name))
    return packages


def cmd_install(args: argparse.Namespace) -> None:
    """Install a package from GitHub releases or CI run artifacts."""
    import subprocess

    from ..shared.models import FetchGithubReleaseCommand

    spec_repo, package, version = parse_install_spec(args.package)
    run_id: str | None = getattr(args, "run_id", None)

    cache_dir = Path.home() / ".uvr" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = str(cache_dir)

    if run_id:
        gh_repo = getattr(args, "repo", None) or spec_repo or infer_gh_repo() or ""
    else:
        gh_repo = resolve_gh_repo(getattr(args, "repo", None), spec_repo)

    # If --run-id, download all wheels from the run upfront into cache
    # (skip if the target wheel is already cached)
    if run_id:
        target_dist = canonicalize_name(package).replace("-", "_")
        already_cached = list(cache_dir.glob(f"{target_dist}-*.whl"))
        if already_cached:
            print(f"Using cached artifacts for {package}.")
        else:
            from ..shared.models import FetchRunArtifactsCommand

            print(f"Downloading artifacts from run {run_id}...")
            fetch = FetchRunArtifactsCommand(
                run_id=run_id,
                dist_name="",  # all wheels
                gh_repo=gh_repo,
                directory=cache,
            )
            result = fetch.execute()
            if result.returncode != 0:
                fatal(f"Failed to download artifacts from run {run_id}.")

    # Discover which packages exist in this repo (for transitive resolution)
    print(f"Discovering packages in {gh_repo}...")
    repo_packages = _list_repo_packages(gh_repo) if gh_repo else set()

    # BFS: fetch the target package, then transitively fetch internal deps
    to_fetch = [package]
    fetched: set[str] = set()
    wheels: list[str] = []

    while to_fetch:
        pkg = to_fetch.pop(0)
        canon = canonicalize_name(pkg)
        if canon in fetched:
            continue
        fetched.add(canon)

        dist_name = canon.replace("-", "_")

        # Check cache — use version-specific glob for the root package
        # when a version is pinned, version-agnostic for transitive deps.
        if pkg == package and version:
            cache_pattern = f"{dist_name}-{version}-*.whl"
        else:
            cache_pattern = f"{dist_name}-*.whl"
        cached = sorted(cache_dir.glob(cache_pattern))
        if cached:
            whl = cached[-1]
            wheels.append(str(whl))
            print(f"  {pkg}: {whl.name} (cached)")
            for dep in _read_internal_deps(whl, repo_packages):
                if dep not in fetched:
                    to_fetch.append(dep)
            continue

        # Not in cache — fetch from GitHub release
        if pkg == package and version:
            tag = f"{pkg}/v{version}"
        else:
            tag = find_latest_remote_release_tag(pkg, gh_repo=gh_repo)
        if not tag:
            print(f"  {pkg}: no release found, skipping", file=sys.stderr)
            continue

        print(f"  {pkg}: downloading release {tag}...")
        fetch = FetchGithubReleaseCommand(
            tag=tag,
            dist_name=dist_name,
            gh_repo=gh_repo,
            directory=cache,
        )
        result = fetch.execute()
        if result.returncode != 0:
            print(f"  {pkg}: download failed, skipping", file=sys.stderr)
            continue

        found = sorted(cache_dir.glob(f"{dist_name}-*.whl"))
        if not found:
            continue

        whl = found[-1]
        wheels.append(str(whl))
        print(f"  {pkg}: {whl.name}")

        # Resolve transitive internal deps
        internal_deps = _read_internal_deps(whl, repo_packages)
        for dep in internal_deps:
            if dep not in fetched:
                to_fetch.append(dep)

    if not wheels:
        fatal(f"No wheels found for '{package}'.")

    extra = getattr(args, "pip_args", [])
    if extra and extra[0] == "--":
        extra = extra[1:]

    print(f"\nInstalling {len(wheels)} wheel(s)...")
    subprocess.run(
        ["uv", "pip", "install", "--find-links", cache, *wheels, *extra],
        check=True,
    )
