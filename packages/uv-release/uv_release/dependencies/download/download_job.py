"""DownloadJob: download wheels from a GitHub release or CI run."""

from __future__ import annotations

from diny import singleton, provider

from ...commands import AnyCommand, MakeDirectoryCommand, ShellCommand
from ...types.job import Job
from ..params.download_params import DownloadParams
from ..shared.github_repo import GitHubRepo
from ..shared.latest_release_tags import LatestReleaseTags


@singleton
class DownloadJob(Job):
    """Download wheels from GitHub."""


@provider(DownloadJob)
def provide_download_job(
    params: DownloadParams,
    github_repo: GitHubRepo,
    latest_release_tags: LatestReleaseTags,
) -> DownloadJob:
    if not params.package and not params.run_id:
        raise ValueError("Specify a package name or --run-id.")

    repo = params.repo or github_repo.name
    if not repo:
        raise ValueError("Could not determine GitHub repo from git remote.")

    commands: list[AnyCommand] = []
    commands.append(
        MakeDirectoryCommand(label=f"Create {params.output}", path=params.output)
    )

    if params.run_id:
        args = [
            "gh",
            "run",
            "download",
            params.run_id,
            "--repo",
            repo,
            "--dir",
            params.output,
        ]
        if params.package:
            args.extend(["--pattern", f"{params.package}*"])
        commands.append(
            ShellCommand(
                label=f"Download artifacts from run {params.run_id}", args=args
            )
        )
    else:
        tag = params.release_tag or latest_release_tags.items.get(params.package, "")
        if not tag:
            raise ValueError(f"No release tag found for {params.package}.")
        dist_name = params.package.replace("-", "_")
        commands.append(
            ShellCommand(
                label=f"Download {params.package} wheels from {tag}",
                args=[
                    "gh",
                    "release",
                    "download",
                    tag,
                    "--repo",
                    repo,
                    "--dir",
                    params.output,
                    "--pattern",
                    f"{dist_name}-*.whl",
                    "--clobber",
                ],
            )
        )

    return DownloadJob(name="download", commands=commands)
