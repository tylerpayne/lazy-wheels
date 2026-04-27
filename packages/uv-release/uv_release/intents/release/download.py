"""DownloadCommands: artifact download commands for release and publish jobs."""

from __future__ import annotations

from diny import provider
from pydantic import BaseModel, ConfigDict

from ...types import Command
from ..shared.jobs import compute_download_commands
from .params import ReleaseParams


class DownloadCommands(BaseModel):
    """Download commands shared by the release and publish jobs."""

    model_config = ConfigDict(frozen=True)

    commands: tuple[Command, ...] = ()


@provider(DownloadCommands)
def compute_download(params: ReleaseParams) -> DownloadCommands:
    """Wrap shared download-commands builder with release params."""
    return DownloadCommands(
        commands=tuple(compute_download_commands(reuse_run=params.reuse_run))
    )
