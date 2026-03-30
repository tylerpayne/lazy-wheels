"""The ``uvr install`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ._common import _fatal


def _parse_install_spec(spec: str) -> tuple[str, str, str | None]:
    """Parse an install spec into (gh_repo, package, version).

    Required form: ``org/repo/package[@version]``
    """
    version: str | None = None
    if "@" in spec:
        spec, version = spec.rsplit("@", 1)

    parts = spec.split("/")
    if len(parts) == 3:
        org, repo, package = parts
        return f"{org}/{repo}", package, version
    else:
        _fatal(
            f"Invalid install spec '{spec}'. "
            "Expected 'org/repo/package', optionally with '@version'.\n"
            "  Example: uvr install myorg/myrepo/my-pkg@1.0.0"
        )


def _find_latest_release_tag(package: str, gh_repo: str | None = None) -> str | None:
    """Return the most recent non-dev release tag for a package.

    Queries GitHub releases for tags matching {package}/v*, excludes -dev tags,
    and returns the one with the highest version number.
    """
    import subprocess

    from packaging.version import Version

    cmd = ["gh", "release", "list", "--json", "tagName", "--limit", "200"]
    if gh_repo:
        cmd.extend(["--repo", gh_repo])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        releases = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    prefix = f"{package}/v"
    tags = [
        r["tagName"]
        for r in releases
        if r["tagName"].startswith(prefix) and not r["tagName"].endswith("-dev")
    ]
    if not tags:
        return None
    return max(tags, key=lambda t: Version(t.split("/v")[-1]))


def cmd_install(args: argparse.Namespace) -> None:
    """Install a package and its transitive internal deps from GitHub releases."""
    import subprocess
    import tempfile

    from packaging.utils import canonicalize_name

    from ..shared.models import FetchGithubReleaseCommand

    gh_repo, package, version = _parse_install_spec(args.package)

    # For now, install only the requested package; pip resolves external deps
    order = [package]

    with tempfile.TemporaryDirectory() as tmp:
        wheels: list[str] = []
        for pkg in order:
            if pkg == package and version:
                tag = f"{pkg}/v{version}"
            else:
                tag = _find_latest_release_tag(pkg, gh_repo=gh_repo)
            if not tag:
                _fatal(f"No release found for '{pkg}'.")

            dist_name = canonicalize_name(pkg).replace("-", "_")
            fetch = FetchGithubReleaseCommand(
                tag=tag,
                dist_name=dist_name,
                directory=tmp,
                label=f"Fetch {pkg}",
            )
            result = fetch.execute()
            if result.returncode != 0:
                _fatal(f"No compatible wheel for '{pkg}' in release {tag}.")

            found = list(Path(tmp).glob(f"{dist_name}-*.whl"))
            if not found:
                _fatal(f"No wheel found for '{pkg}' in release {tag}.")
            wheels.append(str(found[0]))
            print(f"  {found[0].name}")

        print(f"\nInstalling {len(wheels)} wheel(s)...")
        subprocess.run(["uv", "pip", "install", *wheels], check=True)
