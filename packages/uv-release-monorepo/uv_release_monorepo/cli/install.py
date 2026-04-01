"""The ``uvr install`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..shared.utils.cli import (
    fatal,
    infer_gh_repo,
    parse_install_spec,
    resolve_gh_repo,
)
from ..shared.utils.tags import find_latest_remote_release_tag


def cmd_install(args: argparse.Namespace) -> None:
    """Install a package from GitHub releases or CI run artifacts."""
    import subprocess

    from packaging.utils import canonicalize_name

    from ..shared.models import FetchGithubReleaseCommand, FetchRunArtifactsCommand

    spec_repo, package, version = parse_install_spec(args.package)
    run_id: str | None = getattr(args, "run_id", None)

    cache_dir = Path.home() / ".uvr" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = str(cache_dir)

    if run_id:
        # Install from CI run artifacts
        gh_repo = getattr(args, "repo", None) or spec_repo or infer_gh_repo() or ""
        dist_name = canonicalize_name(package).replace("-", "_")
        fetch = FetchRunArtifactsCommand(
            run_id=run_id,
            dist_name=dist_name,
            gh_repo=gh_repo,
            directory=cache,
            label=f"Fetch {package} from run {run_id}",
        )
        result = fetch.execute()
        if result.returncode != 0:
            fatal(f"No compatible wheel for '{package}' in run {run_id}.")

        wheels = [str(w) for w in cache_dir.glob(f"{dist_name}-*.whl")]
        if not wheels:
            fatal(f"No wheel found for '{package}' in run {run_id}.")
        for w in wheels:
            print(f"  {Path(w).name}")
    else:
        # Install from GitHub releases
        gh_repo = resolve_gh_repo(getattr(args, "repo", None), spec_repo)
        wheels = []
        for pkg in [package]:
            if pkg == package and version:
                tag = f"{pkg}/v{version}"
            else:
                tag = find_latest_remote_release_tag(pkg, gh_repo=gh_repo)
            if not tag:
                fatal(f"No release found for '{pkg}'.")

            dist_name = canonicalize_name(pkg).replace("-", "_")
            fetch = FetchGithubReleaseCommand(
                tag=tag,
                dist_name=dist_name,
                directory=cache,
                label=f"Fetch {pkg}",
            )
            result = fetch.execute()
            if result.returncode != 0:
                fatal(f"No compatible wheel for '{pkg}' in release {tag}.")

            found = list(cache_dir.glob(f"{dist_name}-*.whl"))
            if not found:
                fatal(f"No wheel found for '{pkg}' in release {tag}.")
            wheels.append(str(found[0]))
            print(f"  {found[0].name}")

    extra = getattr(args, "pip_args", [])
    # Strip leading "--" separator if present
    if extra and extra[0] == "--":
        extra = extra[1:]

    print(f"\nInstalling {len(wheels)} wheel(s)...")
    subprocess.run(
        ["uv", "pip", "install", "--find-links", cache, *wheels, *extra],
        check=True,
    )
