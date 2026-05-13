"""Version bump strategies."""

from enum import Enum


class BumpKind(Enum):
    """Version bump strategies."""

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    POST = "post"
    DEV = "dev"
    # Pre-release kinds. Same-kind input increments pre_number; higher kind
    # resets to 0; lower kind (e.g. rc -> alpha) is a regression and is rejected.
    ALPHA = "alpha"
    BETA = "beta"
    RC = "rc"
    # Strips pre/dev suffix to produce a clean release.
    STABLE = "stable"
    # Auto-detect the last version section and increment its number.
    AUTO = "auto"
