"""Version parsing and bumping utilities.

Handles conversion between version strings and semver objects, with
special handling for incomplete version strings (e.g., "1.0" → "1.0.0").
"""

from __future__ import annotations

import semver


def parse_version(version_str: str) -> semver.Version:
    """Parse a version string into a semver.Version object.

    Handles incomplete versions by padding with zeros:
    - "1" → "1.0.0"
    - "1.2" → "1.2.0"
    - "1.2.3" → "1.2.3"

    Only the first 3 components are used (major.minor.patch).
    Prerelease/build metadata is not supported.
    """
    parts = version_str.split(".")
    # Pad with zeros to ensure we have at least 3 parts
    while len(parts) < 3:
        parts.append("0")
    return semver.Version.parse(".".join(parts[:3]))


def bump_patch(version_str: str) -> str:
    """Increment the patch version and return as a string.

    Examples:
        "1.2.3" → "1.2.4"
        "1.0" → "1.0.1"
        "2" → "2.0.1"
    """
    return str(parse_version(version_str).bump_patch())
