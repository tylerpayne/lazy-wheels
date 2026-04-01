"""The ``uvr download`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from packaging.utils import canonicalize_name

from ..shared.utils.cli import fatal, parse_install_spec, resolve_gh_repo
from ..shared.utils.tags import find_latest_remote_release_tag


def cmd_wheels(args: argparse.Namespace) -> None:
    """Download platform-compatible wheels from a GitHub release or CI run."""
    from ..shared.models import FetchGithubReleaseCommand, FetchRunArtifactsCommand

    output_dir: str = args.output
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if args.run_id:
        # --run-id: download all wheels from the run's artifacts.
        # package is optional — used to filter if provided.
        if args.package:
            _, package, _ = parse_install_spec(args.package)
            dist_name = canonicalize_name(package).replace("-", "_")
        else:
            package = None
            dist_name = ""  # empty prefix matches all wheels

        from ..shared.utils.cli import infer_gh_repo

        gh_repo = getattr(args, "repo", None) or infer_gh_repo() or ""

        cmd = FetchRunArtifactsCommand(
            run_id=args.run_id,
            dist_name=dist_name,
            gh_repo=gh_repo,
            directory=output_dir,
            label=f"Fetch wheels from run {args.run_id}",
        )
    else:
        if not args.package:
            fatal("Package name required (e.g. my-pkg or my-pkg@1.0.0).")
        spec_repo, package, version = parse_install_spec(args.package)
        gh_repo = resolve_gh_repo(getattr(args, "repo", None), spec_repo)
        dist_name = canonicalize_name(package).replace("-", "_")

        if args.release_tag:
            tag = args.release_tag
        elif version:
            tag = f"{package}/v{version}"
        else:
            tag = find_latest_remote_release_tag(package, gh_repo=gh_repo)
        if not tag:
            fatal(f"No release found for '{package}'.")

        cmd = FetchGithubReleaseCommand(
            tag=tag,
            dist_name=dist_name,
            gh_repo=gh_repo,
            directory=output_dir,
            label=f"Fetch {package} from {tag}",
        )

    result = cmd.execute()
    if result.returncode != 0:
        label = package or f"run {args.run_id}"
        fatal(f"Download failed for '{label}'. See errors above.")

    glob_pattern = f"{dist_name}-*.whl" if dist_name else "*.whl"
    found = list(Path(output_dir).glob(glob_pattern))
    for whl in found:
        print(f"  {whl.name}")
    print(f"\nSaved {len(found)} wheel(s) to {output_dir}/")
