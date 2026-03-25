"""The ``uvr install`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ._common import _discover_packages, _fatal


def _parse_install_spec(spec: str) -> tuple[str | None, str, str | None]:
    """Parse an install spec into (gh_repo, package, version).

    Accepted forms:
      package[@version]              -- local workspace package
      org/repo/package[@version]     -- remote GitHub repo
    """
    version: str | None = None
    if "@" in spec:
        spec, version = spec.rsplit("@", 1)

    parts = spec.split("/")
    if len(parts) == 1:
        return None, parts[0], version
    elif len(parts) == 3:
        org, repo, package = parts
        return f"{org}/{repo}", package, version
    else:
        _fatal(
            f"Invalid install spec '{spec}'. "
            "Expected 'package' or 'org/repo/package', optionally with '@version'."
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

    gh_repo, package, version = _parse_install_spec(args.package)

    if gh_repo is None:
        # Local workspace: resolve transitive internal deps via workspace graph
        packages = _discover_packages()
        if package not in packages:
            _fatal(f"Package '{package}' not found in workspace.")

        order: list[str] = []
        visited: set[str] = set()
        stack = [package]
        while stack:
            pkg = stack.pop()
            if pkg in visited:
                continue
            visited.add(pkg)
            order.append(pkg)
            for dep in packages[pkg][1]:
                if dep not in visited:
                    stack.append(dep)
        order.reverse()  # deps before dependents
    else:
        # Remote: install only the requested package; pip resolves external deps
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

            cmd = [
                "gh",
                "release",
                "download",
                tag,
                "--pattern",
                "*.whl",
                "--dir",
                tmp,
                "--clobber",
            ]
            if gh_repo:
                cmd.extend(["--repo", gh_repo])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                _fatal(f"Failed to download release {tag}: {result.stderr.strip()}")

            found = list(Path(tmp).glob(f"{pkg.replace('-', '_')}-*.whl"))
            if not found:
                _fatal(f"No wheel found for '{pkg}' in release {tag}.")
            wheels.append(str(found[0]))
            print(f"  {found[0].name}")

        print(f"\nInstalling {len(wheels)} wheel(s)...")
        subprocess.run(["uv", "pip", "install", *wheels], check=True)
