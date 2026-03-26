"""Version parsing and bumping utilities.

Handles conversion between version strings and semver objects, with
special handling for incomplete version strings (e.g., "1.0" → "1.0.0")
and PEP 440 dev versions (e.g., "1.0.0.dev0").
"""

from __future__ import annotations

import re

import semver


def strip_dev(version_str: str) -> str:
    """Remove a PEP 440 ``.devN`` suffix if present.

    Examples:
        "1.2.3.dev0" → "1.2.3"
        "1.2.3" → "1.2.3"
    """
    return re.sub(r"\.dev\d*$", "", version_str)


def make_dev(version_str: str) -> str:
    """Add a ``.dev0`` suffix. Idempotent.

    Examples:
        "1.2.3" → "1.2.3.dev0"
        "1.2.3.dev0" → "1.2.3.dev0"
    """
    return f"{strip_dev(version_str)}.dev0"


def parse_version(version_str: str) -> semver.Version:
    """Parse a version string into a semver.Version object.

    Strips any ``.devN`` suffix first, then handles incomplete versions
    by padding with zeros:
    - "1" → "1.0.0"
    - "1.2" → "1.2.0"
    - "1.2.3" → "1.2.3"
    - "1.2.3.dev0" → "1.2.3"
    """
    cleaned = strip_dev(version_str)
    parts = cleaned.split(".")
    while len(parts) < 3:
        parts.append("0")
    return semver.Version.parse(".".join(parts[:3]))


def bump_patch(version_str: str) -> str:
    """Increment the patch version and return as a string.

    Strips any ``.devN`` suffix before bumping.

    Examples:
        "1.2.3" → "1.2.4"
        "1.2.3.dev0" → "1.2.4"
        "1.0" → "1.0.1"
    """
    return str(parse_version(version_str).bump_patch())
