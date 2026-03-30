"""The ``uvr download`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from packaging.utils import canonicalize_name

from ._common import _fatal, _parse_install_spec
from ..shared.utils.tags import find_latest_remote_release_tag


def cmd_wheels(args: argparse.Namespace) -> None:
    """Download platform-compatible wheels from a GitHub release or CI run."""
    from ..shared.models import FetchGithubReleaseCommand, FetchRunArtifactsCommand

    gh_repo, package, version = _parse_install_spec(args.package)
    dist_name = canonicalize_name(package).replace("-", "_")
    output_dir: str = args.output

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if args.run_id:
        cmd = FetchRunArtifactsCommand(
            run_id=args.run_id,
            dist_name=dist_name,
            directory=output_dir,
            label=f"Fetch {package} from run {args.run_id}",
        )
    else:
        if args.release_tag:
            tag = args.release_tag
        elif version:
            tag = f"{package}/v{version}"
        else:
            tag = find_latest_remote_release_tag(package, gh_repo=gh_repo)
        if not tag:
            _fatal(f"No release found for '{package}'.")

        cmd = FetchGithubReleaseCommand(
            tag=tag,
            dist_name=dist_name,
            directory=output_dir,
            label=f"Fetch {package} from {tag}",
        )

    result = cmd.execute()
    if result.returncode != 0:
        _fatal(f"No compatible wheels found for '{package}'.")

    found = list(Path(output_dir).glob(f"{dist_name}-*.whl"))
    for whl in found:
        print(f"  {whl.name}")
    print(f"\nSaved {len(found)} wheel(s) to {output_dir}/")
