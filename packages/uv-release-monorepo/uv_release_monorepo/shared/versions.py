"""Version parsing and bumping utilities.

Handles conversion between version strings and semver objects, with
special handling for incomplete version strings (e.g., "1.0" -> "1.0.0")
and PEP 440 dev/pre/post versions.
"""

from __future__ import annotations

import re

import semver


def strip_dev(version_str: str) -> str:
    """Remove a PEP 440 ``.devN`` suffix if present.

    Examples:
        "1.2.3.dev0" -> "1.2.3"
        "1.2.3" -> "1.2.3"
        "1.2.3.post0.dev0" -> "1.2.3.post0"
    """
    return re.sub(r"\.dev\d*$", "", version_str)


def make_dev(version_str: str) -> str:
    """Add a ``.dev0`` suffix. Idempotent.

    Examples:
        "1.2.3" -> "1.2.3.dev0"
        "1.2.3.dev0" -> "1.2.3.dev0"
        "1.2.3.post0" -> "1.2.3.post0.dev0"
    """
    return f"{strip_dev(version_str)}.dev0"


def bump_dev(version_str: str) -> str:
    """Increment the dev number.

    Examples:
        "1.2.3.dev0" -> "1.2.3.dev1"
        "1.2.3.dev5" -> "1.2.3.dev6"
        "1.2.3" -> "1.2.3.dev0"  (adds .dev0 if not present)
    """
    m = re.search(r"\.dev(\d+)$", version_str)
    if m:
        n = int(m.group(1))
        return version_str[: m.start()] + f".dev{n + 1}"
    return f"{version_str}.dev0"


def dev_number(version_str: str) -> int | None:
    """Extract the dev number from a version string.

    Examples:
        "1.2.3.dev0" -> 0
        "1.2.3.dev5" -> 5
        "1.2.3" -> None
    """
    m = re.search(r"\.dev(\d+)$", version_str)
    return int(m.group(1)) if m else None


def is_dev(version_str: str) -> bool:
    """Check if a version has a .devN suffix."""
    return re.search(r"\.dev\d*$", version_str) is not None


def is_prerelease(version_str: str) -> bool:
    """Check if a version has a pre-release suffix (aN, bN, rcN)."""
    return re.search(r"(a|b|rc)\d+", strip_dev(version_str)) is not None


def is_postrelease(version_str: str) -> bool:
    """Check if a version has a .postN suffix."""
    return ".post" in strip_dev(version_str)


def is_final(version_str: str) -> bool:
    """Check if a version is a plain final release (no dev/pre/post)."""
    v = strip_dev(version_str)
    return not is_prerelease(v) and not is_postrelease(v)


def strip_version(
    version_str: str,
    *,
    dev: bool = False,
    pre: bool = False,
    post: bool = False,
) -> str:
    """Selectively strip PEP 440 suffixes from a version string.

    Args:
        version_str: The version to strip.
        dev: Strip ``.devN`` suffix.
        pre: Strip ``aN``, ``bN``, ``rcN`` suffix.
        post: Strip ``.postN`` suffix.

    Suffixes are stripped in order: dev, post, pre (innermost-out).

    Examples:
        strip_version("1.2.3rc1.dev0", dev=True) -> "1.2.3rc1"
        strip_version("1.2.3rc1.dev0", dev=True, pre=True) -> "1.2.3"
        strip_version("1.2.3.post0.dev0", dev=True, post=True) -> "1.2.3"
        strip_version("1.2.3.post0.dev0", dev=True, pre=True, post=True) -> "1.2.3"
    """
    v = version_str
    if dev:
        v = re.sub(r"\.dev\d*$", "", v)
    if post:
        v = re.sub(r"\.post\d+$", "", v)
    if pre:
        v = re.sub(r"(a|b|rc)\d+$", "", v)
    return v


def base_version(version_str: str) -> str:
    """Strip all dev/pre/post suffixes to get the base X.Y.Z.

    Examples:
        "1.2.3.dev0" -> "1.2.3"
        "1.2.3a1" -> "1.2.3"
        "1.2.3.post0.dev0" -> "1.2.3"
        "1.2.3rc2" -> "1.2.3"
    """
    return strip_version(version_str, dev=True, pre=True, post=True)


def make_pre(version_str: str, kind: str, n: int = 0) -> str:
    """Create a pre-release version.

    Args:
        version_str: Base version (dev suffix stripped).
        kind: One of "a" (alpha), "b" (beta), "rc" (release candidate).
        n: Pre-release number (default 0).

    Examples:
        make_pre("1.2.3.dev2", "a") -> "1.2.3a0"
        make_pre("1.2.3.dev2", "rc", 1) -> "1.2.3rc1"
    """
    return f"{base_version(version_str)}{kind}{n}"


def make_post(version_str: str, n: int = 0) -> str:
    """Create a post-release version.

    Args:
        version_str: Must be a final release version.
        n: Post-release number (default 0).

    Examples:
        make_post("1.2.3") -> "1.2.3.post0"
        make_post("1.2.3", 1) -> "1.2.3.post1"
    """
    return f"{base_version(version_str)}.post{n}"


def next_pre_number(existing_tags: list[str], name: str, kind: str) -> int:
    """Find the next pre-release number by scanning existing tags.

    Examples:
        next_pre_number(["pkg/v1.0.0a0", "pkg/v1.0.0a1"], "pkg", "a") -> 2
        next_pre_number([], "pkg", "a") -> 0
    """
    pattern = re.compile(rf"^{re.escape(name)}/v\d+\.\d+\.\d+{re.escape(kind)}(\d+)$")
    numbers = [int(m.group(1)) for t in existing_tags if (m := pattern.match(t))]
    return max(numbers) + 1 if numbers else 0


def next_post_number(existing_tags: list[str], name: str) -> int:
    """Find the next post-release number by scanning existing tags.

    Examples:
        next_post_number(["pkg/v1.0.0.post0"], "pkg") -> 1
        next_post_number([], "pkg") -> 0
    """
    pattern = re.compile(rf"^{re.escape(name)}/v\d+\.\d+\.\d+\.post(\d+)$")
    numbers = [int(m.group(1)) for t in existing_tags if (m := pattern.match(t))]
    return max(numbers) + 1 if numbers else 0


def version_from_tag(tag: str) -> str:
    """Extract the version string from a release tag.

    Tags follow the pattern ``{package-name}/v{version}``.

    Examples:
        "pkg/v1.0.0" -> "1.0.0"
        "my-pkg/v2.3.4.dev0" -> "2.3.4.dev0"
    """
    return tag.split("/v")[-1]


def tag_for_package(name: str, version: str) -> str:
    """Build a release tag from a package name and version.

    Examples:
        ("pkg", "1.0.0") -> "pkg/v1.0.0"
        ("my-pkg", "2.3.4") -> "my-pkg/v2.3.4"
    """
    return f"{name}/v{version}"


def parse_version(version_str: str) -> semver.Version:
    """Parse a version string into a semver.Version object.

    Strips all dev/pre/post suffixes first, then handles incomplete versions
    by padding with zeros:
    - "1" -> "1.0.0"
    - "1.2" -> "1.2.0"
    - "1.2.3" -> "1.2.3"
    - "1.2.3.dev0" -> "1.2.3"
    - "1.2.3a1" -> "1.2.3"
    """
    cleaned = base_version(version_str)
    parts = cleaned.split(".")
    while len(parts) < 3:
        parts.append("0")
    return semver.Version.parse(".".join(parts[:3]))


def bump_patch(version_str: str) -> str:
    """Increment the patch version and return as a string.

    Strips all dev/pre/post suffixes before bumping.

    Examples:
        "1.2.3" -> "1.2.4"
        "1.2.3.dev0" -> "1.2.4"
        "1.2.3a1" -> "1.2.4"
        "1.0" -> "1.0.1"
    """
    return str(parse_version(version_str).bump_patch())
