"""The ``uvr install`` command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from packaging.utils import canonicalize_name

from ._args import CommandArgs
from .download import _find_latest_release_tag, _infer_gh_repo


class InstallArgs(CommandArgs):
    """Typed arguments for ``uvr install``."""

    packages: list[str] | None = None
    run_id: str | None = None
    repo: str | None = None
    dist: str | None = None


def cmd_install(args: argparse.Namespace) -> None:
    """Install packages from GitHub releases, CI artifacts, or local wheels."""
    parsed = InstallArgs.from_namespace(args)

    # --dist: install from a local wheel directory
    if parsed.dist is not None:
        dist_dir = Path(parsed.dist)
        if not dist_dir.is_dir():
            print(f"ERROR: Directory not found: {dist_dir}", file=sys.stderr)
            sys.exit(1)

        if parsed.packages:
            wheels: list[str] = []
            for spec in parsed.packages:
                name = spec.split("@")[0]
                dist_name = canonicalize_name(name).replace("-", "_")
                found = sorted(dist_dir.glob(f"{dist_name}-*.whl"))
                if not found:
                    print(
                        f"ERROR: No wheel found for '{name}' in {dist_dir}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                wheels.append(str(found[-1]))
                print(f"  {name}: {found[-1].name}")
        else:
            wheels = [str(w) for w in sorted(dist_dir.glob("*.whl"))]
            if not wheels:
                print(f"ERROR: No wheels found in {dist_dir}", file=sys.stderr)
                sys.exit(1)
            for w in wheels:
                print(f"  {Path(w).name}")

        print(f"\nInstalling {len(wheels)} wheel(s) from {dist_dir}...")
        subprocess.run(
            ["uv", "pip", "install", "--find-links", str(dist_dir), *wheels],
            check=True,
        )
        return

    # GitHub release mode
    if not parsed.packages and not parsed.run_id:
        print("ERROR: Specify at least one package, or use --run-id.", file=sys.stderr)
        sys.exit(1)

    gh_repo = parsed.repo or _infer_gh_repo() or ""
    cache_dir = Path.home() / ".uvr" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    wheels = []
    for spec in parsed.packages or []:
        name, version = _parse_spec(spec)
        canon = canonicalize_name(name)
        dist_name = canon.replace("-", "_")

        if version:
            tag = f"{name}/v{version}"
        else:
            tag = _find_latest_release_tag(name, gh_repo)
        if not tag:
            print(f"  {name}: no release found, skipping", file=sys.stderr)
            continue

        print(f"  {name}: downloading release {tag}...")
        result = subprocess.run(
            [
                "gh",
                "release",
                "download",
                tag,
                "--repo",
                gh_repo,
                "--dir",
                str(cache_dir),
                "--pattern",
                f"{dist_name}-*.whl",
                "--clobber",
            ],
        )
        if result.returncode != 0:
            print(f"  {name}: download failed, skipping", file=sys.stderr)
            continue

        found = sorted(cache_dir.glob(f"{dist_name}-*.whl"))
        if found:
            wheels.append(str(found[-1]))

    if not wheels:
        print("ERROR: No wheels downloaded.", file=sys.stderr)
        sys.exit(1)

    print(f"\nInstalling {len(wheels)} wheel(s)...")
    subprocess.run(
        ["uv", "pip", "install", "--find-links", str(cache_dir), *wheels],
        check=True,
    )


def _parse_spec(spec: str) -> tuple[str, str]:
    """Parse 'pkg' or 'pkg@version' into (name, version)."""
    if "@" in spec:
        name, version = spec.split("@", 1)
        return name, version
    return spec, ""
