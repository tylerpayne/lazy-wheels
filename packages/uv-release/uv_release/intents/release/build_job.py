"""ReleaseBuildJob: build job for the release pipeline."""

from __future__ import annotations

from diny import provider
from pydantic import BaseModel, ConfigDict

from ...states.release_tags import ReleaseTags
from ...states.uvr_state import UvrState
from ...states.workspace import Workspace
from ...types import Job
from ..shared.jobs import compute_build_job
from .params import ReleaseParams
from .releases import Releases


class ReleaseBuildJob(BaseModel):
    """Build job for the release pipeline."""

    model_config = ConfigDict(frozen=True)

    job: Job = Job(name="build")


@provider(ReleaseBuildJob)
def compute_release_build_job(
    workspace: Workspace,
    releases: Releases,
    release_tags: ReleaseTags,
    uvr_state: UvrState,
    params: ReleaseParams,
) -> ReleaseBuildJob:
    """Compute the build job, or return an empty job if skipped."""
    if "build" in params.skip or params.reuse_run:
        return ReleaseBuildJob()
    return ReleaseBuildJob(
        job=compute_build_job(
            workspace, releases.items, release_tags, uvr_state.runners
        )
    )
