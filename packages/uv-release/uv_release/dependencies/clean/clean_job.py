"""CleanJob: remove build caches."""

from __future__ import annotations

from pathlib import Path

from diny import singleton, provider

from ...commands import RemoveDirectoryCommand
from ...types.job import Job
from ..shared.workspace_packages import WorkspacePackages


@singleton
class CleanJob(Job):
    """Remove build cache directories."""


@provider(CleanJob)
def provide_clean_job(workspace_packages: WorkspacePackages) -> CleanJob:
    root = workspace_packages.root
    cache_dirs = [
        root / ".uvr" / "cache",
        Path.home() / ".uvr" / "cache",
    ]
    commands = [
        RemoveDirectoryCommand(label=f"Remove {d}", path=str(d))
        for d in cache_dirs
        if d.exists()
    ]
    return CleanJob(name="clean", commands=commands)
