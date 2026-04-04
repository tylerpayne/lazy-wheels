"""The ``uvr install`` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zipfile import ZipFile

from packaging.metadata import Metadata
from packaging.utils import canonicalize_name

from ._args import CommandArgs
from ..shared.utils.cli import (
    fatal,
    infer_gh_repo,
    parse_install_spec,
    resolve_gh_repo,
)
from ..shared.utils.tags import find_latest_remote_release_tag


class InstallArgs(CommandArgs):
    """Typed arguments for ``uvr install``."""

    packages: list[str] | None = None
    run_id: str | None = None
    repo: str | None = None
    dist: str | None = None
    pip_args: list[str] = []


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
    """Install packages from GitHub releases, CI run artifacts, or local wheels."""
    import subprocess

    from ..shared.models import FetchGithubReleaseCommand

    parsed = InstallArgs.from_namespace(args)

    # --dist: install from a local wheel directory
    if parsed.dist is not None:
        dist_dir = Path(parsed.dist)
        if not dist_dir.is_dir():
            fatal(f"Directory not found: {dist_dir}")

        package_specs = parsed.packages or []
        if package_specs:
            # Filter to requested packages
            wheels: list[str] = []
            for spec in package_specs:
                name = spec.split("@")[0]
                dist_name = canonicalize_name(name).replace("-", "_")
                found = sorted(dist_dir.glob(f"{dist_name}-*.whl"))
                if not found:
                    fatal(f"No wheel found for '{name}' in {dist_dir}")
                wheels.append(str(found[-1]))
                print(f"  {name}: {found[-1].name}")
        else:
            # Install all wheels in the directory
            wheels = [str(w) for w in sorted(dist_dir.glob("*.whl"))]
            if not wheels:
                fatal(f"No wheels found in {dist_dir}")
            for w in wheels:
                print(f"  {Path(w).name}")

        extra = list(parsed.pip_args)
        if extra and extra[0] == "--":
            extra = extra[1:]

        print(f"\nInstalling {len(wheels)} wheel(s) from {dist_dir}...")
        subprocess.run(
            ["uv", "pip", "install", "--find-links", str(dist_dir), *wheels, *extra],
            check=True,
        )
        return

    # Parse all package specs
    package_specs = parsed.packages or []
    pinned_versions: dict[str, str] = {}  # canon name → version
    root_packages: list[str] = []
    spec_repo: str | None = None

    for spec in package_specs:
        sr, pkg, ver = parse_install_spec(spec)
        if sr and not spec_repo:
            spec_repo = sr
        root_packages.append(pkg)
        if ver:
            pinned_versions[canonicalize_name(pkg)] = ver

    run_id: str | None = parsed.run_id

    if not root_packages and not run_id:
        fatal("Specify at least one package, or use --run-id to install all.")

    cache_dir = Path.home() / ".uvr" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = str(cache_dir)

    if run_id:
        gh_repo = parsed.repo or spec_repo or infer_gh_repo() or ""
    else:
        gh_repo = resolve_gh_repo(parsed.repo, spec_repo)

    # If --run-id, download all wheels from the run upfront into cache
    if run_id:
        # Skip if all root packages are already cached (or no packages specified)
        all_cached = root_packages and all(
            list(cache_dir.glob(f"{canonicalize_name(p).replace('-', '_')}-*.whl"))
            for p in root_packages
        )
        if all_cached:
            print("Using cached artifacts.")
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

        # If no packages specified, install all wheels from the run
        if not root_packages:
            wheels = [str(w) for w in sorted(cache_dir.glob("*.whl"))]
            if not wheels:
                fatal("No wheels found in run artifacts.")
            for w in wheels:
                print(f"  {Path(w).name}")

            extra = list(parsed.pip_args)
            if extra and extra[0] == "--":
                extra = extra[1:]

            print(f"\nInstalling {len(wheels)} wheel(s)...")
            subprocess.run(
                ["uv", "pip", "install", "--find-links", cache, *wheels, *extra],
                check=True,
            )
            return

    # Discover which packages exist in this repo (for transitive resolution)
    print(f"Discovering packages in {gh_repo}...")
    repo_packages = _list_repo_packages(gh_repo) if gh_repo else set()

    # BFS: fetch all requested packages, then transitively fetch internal deps
    to_fetch = list(root_packages)
    fetched: set[str] = set()
    wheels: list[str] = []

    while to_fetch:
        pkg = to_fetch.pop(0)
        canon = canonicalize_name(pkg)
        if canon in fetched:
            continue
        fetched.add(canon)

        dist_name = canon.replace("-", "_")

        # Check cache — use version-specific glob for pinned packages
        pinned = pinned_versions.get(canon)
        if pinned:
            cache_pattern = f"{dist_name}-{pinned}-*.whl"
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
        if pinned:
            tag = f"{pkg}/v{pinned}"
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
        names = ", ".join(root_packages)
        fatal(f"No wheels found for: {names}")

    extra = list(parsed.pip_args)
    if extra and extra[0] == "--":
        extra = extra[1:]

    print(f"\nInstalling {len(wheels)} wheel(s)...")
    subprocess.run(
        ["uv", "pip", "install", "--find-links", cache, *wheels, *extra],
        check=True,
    )
