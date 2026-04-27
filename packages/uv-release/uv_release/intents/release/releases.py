"""Releases: computed release versions for changed packages."""

from __future__ import annotations

from diny import provider
from pydantic import BaseModel, ConfigDict, Field

from ...states.changes import Changes
from ...states.uvr_state import UvrState
from ...types import Release
from ..shared.versioning import compute_next_version, compute_release_version
from .params import ReleaseParams


class Releases(BaseModel):
    """Computed releases for the current pipeline run."""

    model_config = ConfigDict(frozen=True)

    items: dict[str, Release] = Field(default_factory=dict)


@provider(Releases)
def compute_releases(
    changes: Changes, uvr_state: UvrState, params: ReleaseParams
) -> Releases:
    """Compute a Release for each changed package."""
    releases: dict[str, Release] = {}
    for change in changes.items:
        name = change.package.name
        release_version = compute_release_version(
            change.package.version, dev_release=params.dev_release
        )
        next_version = compute_next_version(
            change.package.version, dev_release=params.dev_release
        )
        notes = params.release_notes.get(name, change.commit_log)
        releases[name] = Release(
            package=change.package,
            release_version=release_version,
            next_version=next_version,
            release_notes=notes,
            make_latest=(name == uvr_state.config.latest_package),
        )
    return Releases(items=releases)
