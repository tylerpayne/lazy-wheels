"""The ``uvr install`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from ._common import _fatal, _parse_install_spec
from ..shared.utils.tags import find_latest_remote_release_tag


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
                tag = find_latest_remote_release_tag(pkg, gh_repo=gh_repo)
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
