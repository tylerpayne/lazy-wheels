"""BuildMatrix: CI runner matrix for the release pipeline."""

from __future__ import annotations

from diny import provider
from pydantic import BaseModel, ConfigDict, Field

from ...states.uvr_state import UvrState
from .releases import Releases


class BuildMatrix(BaseModel):
    """Unique runner sets for the CI build matrix."""

    model_config = ConfigDict(frozen=True)

    runners: list[list[str]] = Field(default_factory=lambda: [["ubuntu-latest"]])


@provider(BuildMatrix)
def compute_build_matrix(releases: Releases, uvr_state: UvrState) -> BuildMatrix:
    """Collect unique runner sets from release packages."""
    runner_sets: list[list[str]] = []
    for name in releases.items:
        pkg_runners = uvr_state.runners.get(name, [["ubuntu-latest"]])
        for runner in pkg_runners:
            if runner not in runner_sets:
                runner_sets.append(runner)
    return BuildMatrix(runners=runner_sets or [["ubuntu-latest"]])
