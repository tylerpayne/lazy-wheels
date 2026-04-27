"""ReleaseIntent: plan and execute a full release."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ...states.uvr_state import UvrState
from ...states.worktree import Worktree
from ...types import Job, Plan, UserRecoverableError
from .build_job import ReleaseBuildJob
from .build_matrix import BuildMatrix
from .bump_job import BumpJob
from .params import ReleaseParams
from .publish_job import PublishJob
from .release_job import ReleaseJob
from .releases import Releases
from .version_fix import VersionFix


class ReleaseIntent(BaseModel):
    """Intent to release changed packages."""

    model_config = ConfigDict(frozen=True)

    type: Literal["release"] = "release"

    def guard(
        self, *, worktree: Worktree, version_fix: VersionFix, params: ReleaseParams
    ) -> None:
        """Check preconditions. Raises ValueError on failure."""
        if worktree.is_dirty:
            msg = "Working tree is not clean. Commit or stash changes first."
            raise ValueError(msg)
        if params.target == "ci" and worktree.is_ahead_or_behind:
            msg = "Local HEAD differs from remote. Pull or push first."
            raise ValueError(msg)
        if version_fix.group is not None:
            raise UserRecoverableError(
                "Some packages have dev versions that need to be set to stable.",
                fix=version_fix.group,
            )

    def plan(
        self,
        *,
        releases: Releases,
        release_build_job: ReleaseBuildJob,
        release_job: ReleaseJob,
        publish_job: PublishJob,
        bump_job: BumpJob,
        build_matrix: BuildMatrix,
        uvr_state: UvrState,
        params: ReleaseParams,
    ) -> Plan:
        """(state, intent) -> plan. Full release pipeline."""
        if not releases.items:
            return Plan()

        jobs = [
            Job(name="validate"),
            release_build_job.job,
            release_job.job,
            publish_job.job,
            bump_job.job,
        ]
        skip = [j.name for j in jobs if not j.commands and j.name != "validate"]

        return Plan(
            build_matrix=build_matrix.runners,
            python_version=uvr_state.config.python_version,
            publish_environment=uvr_state.publishing.environment,
            skip=sorted(skip),
            reuse_run=params.reuse_run,
            reuse_release=params.reuse_release,
            jobs=jobs,
        )
