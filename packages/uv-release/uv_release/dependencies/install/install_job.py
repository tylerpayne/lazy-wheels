"""InstallJob: install packages from wheels."""

from __future__ import annotations

from diny import singleton, provider

from ...commands import (
    AnyCommand,
    InstallWheelsCommand,
    MakeDirectoryCommand,
    ShellCommand,
)
from ...types.job import Job
from ...utils.deps import parse_dep_name
from ..params.install_params import InstallParams
from ..shared.github_repo import GitHubRepo
from ..shared.latest_release_tags import LatestReleaseTags


@singleton
class InstallJob(Job):
    """Download and install wheels."""


@provider(InstallJob)
def provide_install_job(
    params: InstallParams,
    github_repo: GitHubRepo,
    latest_release_tags: LatestReleaseTags,
) -> InstallJob:
    if not params.packages and not params.dist:
        raise ValueError("Specify packages to install or --dist directory.")

    commands: list[AnyCommand] = []

    if params.dist:
        commands.append(
            InstallWheelsCommand(
                label=f"Install from {params.dist}", dist_dir=params.dist
            )
        )
    else:
        repo = params.repo or github_repo.name
        if not repo:
            raise ValueError("Could not determine GitHub repo from git remote.")

        cache_dir = ".uvr/cache/install"
        commands.append(MakeDirectoryCommand(label="Create cache", path=cache_dir))

        for pkg_spec in params.packages:
            name = parse_dep_name(pkg_spec)
            tag = latest_release_tags.items.get(name, "")
            if not tag:
                raise ValueError(f"No release tag found for {name}.")
            dist_name = name.replace("-", "_")
            commands.append(
                ShellCommand(
                    label=f"Download {name} from {tag}",
                    args=[
                        "gh",
                        "release",
                        "download",
                        tag,
                        "--repo",
                        repo,
                        "--dir",
                        cache_dir,
                        "--pattern",
                        f"{dist_name}-*.whl",
                        "--clobber",
                    ],
                )
            )

        commands.append(
            InstallWheelsCommand(label="Install wheels", dist_dir=cache_dir)
        )

    return InstallJob(name="install", commands=commands)
