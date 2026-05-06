"""Version bump strategies."""

from enum import Enum


class BumpKind(Enum):
    """Version bump strategies."""

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    POST = "post"
    DEV = "dev"
    # Strips pre/dev suffix to produce a clean release.
    STABLE = "stable"
    # Auto-detect the last version section and increment its number.
    AUTO = "auto"
