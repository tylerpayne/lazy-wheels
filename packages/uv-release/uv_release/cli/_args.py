"""Shared argument model infrastructure for typed CLI args."""

from __future__ import annotations

import argparse
from typing import Self

from pydantic import BaseModel, ConfigDict


class CommandArgs(BaseModel):
    """Base class for typed CLI argument models.

    Subclasses define fields matching argparse dest names.
    Use ``from_namespace()`` to convert an argparse.Namespace.
    """

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        extra="ignore",
    )

    @classmethod
    def from_namespace(cls, namespace: argparse.Namespace) -> Self:
        """Validate and convert an argparse Namespace to this model."""
        return cls.model_validate(vars(namespace))
