"""ReleaseParams: intent-specific configuration for the release pipeline."""

from __future__ import annotations

from typing import Literal

from diny import singleton
from pydantic import BaseModel, ConfigDict, Field


@singleton
class ReleaseParams(BaseModel):
    """Release pipeline configuration. Seeded by CLI via provide()."""

    model_config = ConfigDict(frozen=True)

    dev_release: bool = False
    release_notes: dict[str, str] = Field(default_factory=dict)
    target: Literal["ci", "local"] = "local"
    skip: frozenset[str] = frozenset()
    reuse_run: str = ""
    reuse_release: bool = False
