"""VersionMode: which version operation was requested."""

from enum import Enum

from diny import singleton

from ...types.base import Frozen


class VersionOp(Enum):
    """The operation mode for uvr version."""

    READ = "read"
    SET = "set"
    BUMP = "bump"


@singleton
class VersionMode(Frozen):
    """Seeded by CLI. Which version operation to perform."""

    value: VersionOp = VersionOp.READ
