"""BuildIntent: build changed packages locally."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..states.changes import Changes
from ..states.release_tags import ReleaseTags
from ..states.uvr_state import UvrState
from ..states.workspace import Workspace
from ..types import Plan, Release
from .shared.jobs import compute_build_job
from .shared.versioning import compute_release_version


class BuildIntent(BaseModel):
    """Intent to build changed packages."""

    model_config = ConfigDict(frozen=True)

    type: Literal["build"] = "build"

    def guard(self, *, workspace: Workspace) -> None:
        """Check preconditions. No-op for build."""

    def plan(
        self,
        *,
        workspace: Workspace,
        uvr_state: UvrState,
        changes: Changes,
        release_tags: ReleaseTags,
    ) -> Plan:
        """(state, intent) -> plan."""
        if not changes.items:
            return Plan()

        releases: dict[str, Release] = {}
        for change in changes.items:
            release_version = compute_release_version(
                change.package.version, dev_release=True
            )
            releases[change.package.name] = Release(
                package=change.package,
                release_version=release_version,
                next_version=change.package.version,
            )

        build_job = compute_build_job(
            workspace, releases, release_tags, uvr_state.runners
        )
        return Plan(jobs=[build_job])
