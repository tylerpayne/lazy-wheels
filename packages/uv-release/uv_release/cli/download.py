"""The ``uvr download`` command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from packaging.utils import canonicalize_name

from ._args import CommandArgs


class DownloadArgs(CommandArgs):
    """Typed arguments for ``uvr download``."""

    output: str = "dist"
    run_id: str | None = None
    package: str | None = None
    release_tag: str | None = None
    repo: str | None = None
    all_platforms: bool = False


def cmd_download(args: argparse.Namespace) -> None:
    """Download wheels from a GitHub release or CI run."""
    parsed = DownloadArgs.from_namespace(args)

    output_dir = Path(parsed.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    gh_repo = parsed.repo or _infer_gh_repo() or ""

    if parsed.run_id:
        dist_name = ""
        if parsed.package:
            dist_name = canonicalize_name(parsed.package).replace("-", "_")

        _download_run_artifacts(
            run_id=parsed.run_id,
            dist_name=dist_name,
            gh_repo=gh_repo,
            output_dir=str(output_dir),
        )
    else:
        if not parsed.package:
            print("ERROR: Package name required.", file=sys.stderr)
            sys.exit(1)

        package = parsed.package
        dist_name = canonicalize_name(package).replace("-", "_")

        if parsed.release_tag:
            tag = parsed.release_tag
        else:
            tag = _find_latest_release_tag(package, gh_repo)
        if not tag:
            print(f"ERROR: No release found for '{package}'.", file=sys.stderr)
            sys.exit(1)

        result = subprocess.run(
            [
                "gh",
                "release",
                "download",
                tag,
                "--repo",
                gh_repo,
                "--dir",
                str(output_dir),
                "--pattern",
                f"{dist_name}-*.whl",
                "--clobber",
            ],
        )
        if result.returncode != 0:
            print(f"ERROR: Download failed for '{package}'.", file=sys.stderr)
            sys.exit(1)

    glob_pattern = f"{dist_name}-*.whl" if dist_name else "*.whl"
    found = list(output_dir.glob(glob_pattern))
    for whl in found:
        print(f"  {whl.name}")
    print(f"\nSaved {len(found)} wheel(s) to {output_dir}/")


def _download_run_artifacts(
    run_id: str, dist_name: str, gh_repo: str, output_dir: str
) -> None:
    """Download wheel artifacts from a CI run."""
    cmd = ["gh", "run", "download", run_id, "--repo", gh_repo, "--dir", output_dir]
    if dist_name:
        cmd.extend(["--pattern", f"*{dist_name}*"])
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(
            f"ERROR: Failed to download artifacts from run {run_id}.", file=sys.stderr
        )
        sys.exit(1)


def _find_latest_release_tag(package: str, gh_repo: str) -> str | None:
    """Find the latest release tag for a package via gh CLI."""
    import json

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
            "50",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        releases = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None

    prefix = f"{package}/v"
    tags = [r["tagName"] for r in releases if r["tagName"].startswith(prefix)]
    return tags[0] if tags else None


def _infer_gh_repo() -> str | None:
    """Infer GitHub repo from git remote."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None
