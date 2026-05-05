"""Version bump strategies."""

from enum import Enum


class BumpKind(Enum):
    """Version bump strategies."""

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    ALPHA = "alpha"
    BETA = "beta"
    RC = "rc"
    POST = "post"
    DEV = "dev"
    # Strips pre/dev suffix to produce a clean release.
    STABLE = "stable"
    # Advance to the next release stage: dev->a, a->b, b->rc, rc->final.
    PROMOTE = "promote"
    # Auto-detect the last version section and increment its number.
    AUTO = "auto"
