"""Version parsing and bumping utilities.

Uses ``packaging.version.Version`` for PEP 440 parsing and comparison,
and ``semver`` for major/minor/patch arithmetic.
"""

from __future__ import annotations

import semver
from packaging.version import InvalidVersion
from packaging.version import Version as PkgVersion


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse(version_str: str) -> PkgVersion:
    """Parse a version string into a ``packaging.version.Version``."""
    return PkgVersion(version_str)


def _format_version(
    release: tuple[int, ...],
    *,
    pre: tuple[str, int] | None = None,
    post: int | None = None,
    dev: int | None = None,
) -> str:
    """Build a PEP 440 version string from components."""
    result = ".".join(str(x) for x in release)
    if pre is not None:
        result += f"{pre[0]}{pre[1]}"
    if post is not None:
        result += f".post{post}"
    if dev is not None:
        result += f".dev{dev}"
    return result


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


def is_dev(version_str: str) -> bool:
    """Check if a version has a .devN suffix."""
    return _parse(version_str).dev is not None


def is_pre(version_str: str) -> bool:
    """Check if a version has an alpha, beta, or rc suffix."""
    return _parse(version_str).pre is not None


def is_post(version_str: str) -> bool:
    """Check if a version has a .postN suffix (ignoring any trailing .devN)."""
    return _parse(version_str).post is not None


# ---------------------------------------------------------------------------
# Stripping / extraction
# ---------------------------------------------------------------------------


def strip_dev(version_str: str) -> str:
    """Remove a PEP 440 ``.devN`` suffix if present.

    Examples:
        "1.2.3.dev0" -> "1.2.3"
        "1.2.3" -> "1.2.3"
        "1.2.3.post0.dev0" -> "1.2.3.post0"
    """
    v = _parse(version_str)
    return _format_version(v.release, pre=v.pre, post=v.post)


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
    """
    v = _parse(version_str)
    return _format_version(
        v.release,
        pre=None if pre else v.pre,
        post=None if post else v.post,
        dev=None if dev else v.dev,
    )


def get_base_version(version_str: str) -> str:
    """Strip all dev/pre/post suffixes to get the base X.Y.Z.

    Examples:
        "1.2.3.dev0" -> "1.2.3"
        "1.2.3a1" -> "1.2.3"
        "1.2.3.post0.dev0" -> "1.2.3"
        "1.2.3rc2" -> "1.2.3"
    """
    return _format_version(_parse(version_str).release)


def extract_pre_kind(version_str: str) -> str:
    """Extract the pre-release kind (a, b, rc) from a version string.

    Returns an empty string if no pre-release suffix is present.

    Examples:
        "1.2.3a1" -> "a"
        "1.2.3b0.dev0" -> "b"
        "1.2.3rc2" -> "rc"
        "1.2.3.dev0" -> ""
    """
    v = _parse(version_str)
    if v.pre is not None:
        return v.pre[0]
    return ""


# ---------------------------------------------------------------------------
# Construction / bumping
# ---------------------------------------------------------------------------


def make_dev(version_str: str) -> str:
    """Add a ``.dev0`` suffix. Idempotent.

    Examples:
        "1.2.3" -> "1.2.3.dev0"
        "1.2.3.dev0" -> "1.2.3.dev0"
        "1.2.3.post0" -> "1.2.3.post0.dev0"
    """
    v = _parse(version_str)
    return _format_version(v.release, pre=v.pre, post=v.post, dev=0)


def bump_dev(version_str: str) -> str:
    """Increment the dev number.

    Examples:
        "1.2.3.dev0" -> "1.2.3.dev1"
        "1.2.3.dev5" -> "1.2.3.dev6"
        "1.2.3" -> "1.2.3.dev0"  (adds .dev0 if not present)
    """
    v = _parse(version_str)
    n = v.dev if v.dev is not None else -1
    return _format_version(v.release, pre=v.pre, post=v.post, dev=n + 1)


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
    return _format_version(_parse(version_str).release, pre=(kind, n))


def make_post(version_str: str, n: int = 0) -> str:
    """Create a post-release version.

    Args:
        version_str: Must be a final release version.
        n: Post-release number (default 0).

    Examples:
        make_post("1.2.3") -> "1.2.3.post0"
        make_post("1.2.3", 1) -> "1.2.3.post1"
    """
    return _format_version(_parse(version_str).release, post=n)


# ---------------------------------------------------------------------------
# Semver parsing and major/minor/patch bumps
# ---------------------------------------------------------------------------

_PRE_KIND_ORDER = {"a": 0, "b": 1, "rc": 2}


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
    r = _parse(version_str).release
    major = r[0]
    minor = r[1] if len(r) > 1 else 0
    patch = r[2] if len(r) > 2 else 0
    return semver.Version(major=major, minor=minor, patch=patch)


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


def bump_minor(version_str: str) -> str:
    """Increment the minor version, reset patch, and return as a string.

    Strips all dev/pre/post suffixes before bumping.

    Examples:
        "1.2.3" -> "1.3.0"
        "1.2.3.dev0" -> "1.3.0"
        "1.2.3a1" -> "1.3.0"
        "0.0.0" -> "0.1.0"
    """
    return str(parse_version(version_str).bump_minor())


def bump_major(version_str: str) -> str:
    """Increment the major version, reset minor and patch, and return as a string.

    Strips all dev/pre/post suffixes before bumping.

    Examples:
        "1.2.3" -> "2.0.0"
        "0.5.2.dev0" -> "1.0.0"
        "0.5.2a3" -> "1.0.0"
    """
    return str(parse_version(version_str).bump_major())


# ---------------------------------------------------------------------------
# Tag helpers
# ---------------------------------------------------------------------------


def parse_tag_version(tag: str) -> str:
    """Extract the version string from a release tag.

    Tags follow the pattern ``{package-name}/v{version}``.

    Examples:
        "pkg/v1.0.0" -> "1.0.0"
        "my-pkg/v2.3.4.dev0" -> "2.3.4.dev0"
    """
    return tag.split("/v")[-1]


def find_previous_release(
    version_str: str,
    name: str,
    repo: object,
) -> str | None:
    """Find the highest released version below the current version.

    Discovers all ``{name}/v*`` tags in *repo*, parses them as PEP 440
    versions, and returns the highest one that sorts below the target
    (``strip_dev(version_str)``).  Tags with a ``-base`` suffix are
    ignored (they are development baselines, not releases).

    Args:
        version_str: Current version (with or without .devN suffix).
        name: Package name for tag prefix.
        repo: pygit2.Repository for ref lookups.

    Returns:
        The previous release version string, or None if not found.
    """
    from pathlib import Path

    target = _parse(strip_dev(version_str))

    # Collect all release tags for this package
    tag_prefix = f"refs/tags/{name}/v"
    candidates: list[tuple[PkgVersion, str]] = []

    # Fast path: filesystem glob
    try:
        tag_dir = Path(repo.path) / "refs" / "tags" / name  # type: ignore[union-attr]
        if tag_dir.is_dir():
            for path in tag_dir.rglob("v*"):
                if path.name.endswith("-base"):
                    continue
                ver_str = path.name[1:]  # strip leading "v"
                try:
                    v = _parse(ver_str)
                except InvalidVersion:
                    continue
                if v < target:
                    candidates.append((v, ver_str))
    except (AttributeError, OSError):
        pass

    # Fallback: pygit2 ref scan (for packed refs or mock repos)
    if not candidates:
        for ref in repo.listall_references():  # type: ignore[union-attr]
            if not ref.startswith(tag_prefix) or ref.endswith("-base"):
                continue
            ver_str = ref.split("/v")[-1]
            try:
                v = _parse(ver_str)
            except InvalidVersion:
                continue
            if v < target:
                candidates.append((v, ver_str))

    if not candidates:
        return None

    # Highest version below target
    candidates.sort(reverse=True)
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Baseline resolution
# ---------------------------------------------------------------------------


def resolve_baseline(
    current_version: str,
    release_type: str,
    name: str,
    repo: object,
) -> str | None:
    """Determine the baseline tag for change detection.

    Given the current pyproject.toml version and the requested release type,
    returns the tag to diff against for determining which packages changed.

    Args:
        current_version: Version string from pyproject.toml.
        release_type: One of "stable", "dev", "pre", "post".
        name: Package name (for tag prefix).
        repo: pygit2.Repository for ref lookups.

    Returns:
        Baseline tag string (e.g. "pkg/v1.0.0" or "pkg/v1.0.1.dev0-base"),
        or None if no previous release exists (package is new).

    Raises:
        ValueError: If the (current_version, release_type) combination is invalid.
    """
    v = _parse(current_version)
    has_dev = v.dev is not None
    has_pre = _parse(strip_dev(current_version)).pre is not None
    has_post = v.post is not None

    # --- Clean version (no .dev suffix) ---
    if not has_dev:
        prev = find_previous_release(current_version, name, repo)
        if prev is None:
            return None
        return f"{name}/v{prev}"

    # --- Dev version ---

    # Validate: post-release dev + final/minor/major/pre → invalid
    if has_post and release_type in ("stable", "pre"):
        msg = (
            f"Cannot {release_type}-release from post-release version {current_version}"
        )
        raise ValueError(msg)

    # Validate: non-post dev + post → invalid
    if not has_post and release_type == "post":
        msg = f"Cannot post-release from unreleased version {current_version}"
        raise ValueError(msg)

    # Dev release → always use current version's own -base tag
    if release_type == "dev":
        return f"{name}/v{current_version}-base"

    # Validate: --pre requires a pre-release suffix in the version
    if release_type == "pre" and not has_pre:
        msg = (
            f"Cannot --pre release from version {current_version} "
            f"— no pre-release suffix. Use 'uvr bump --pre {{a,b,rc}}' first."
        )
        raise ValueError(msg)

    # Pre-release → incremental from dev0 baseline (kind is in the version)
    if has_pre and release_type == "pre":
        if v.dev is not None and v.dev > 0:
            return f"{name}/v{strip_dev(current_version)}.dev0-base"
        return f"{name}/v{current_version}-base"

    # Final/minor/major from pre-release dev → cumulative since last final
    if has_pre and release_type in ("stable",):
        base = get_base_version(current_version)
        prev = find_previous_release(base, name, repo)
        if prev is None:
            return None
        return f"{name}/v{prev}"

    # Post-release dev + post → use dev0 baseline
    if has_post and release_type == "post":
        if v.dev is not None and v.dev > 0:
            # devN (N > 0) → rewind to dev0-base
            return f"{name}/v{strip_dev(current_version)}.dev0-base"
        return f"{name}/v{current_version}-base"

    # Final dev (X.X.X.devN) + non-dev release → use dev0 baseline
    if v.dev is not None and v.dev > 0:
        # devN (N > 0) → rewind to dev0-base
        return f"{name}/v{strip_dev(current_version)}.dev0-base"

    # dev0 → current baseline
    return f"{name}/v{current_version}-base"


# ---------------------------------------------------------------------------
# Bump validation
# ---------------------------------------------------------------------------


def validate_bump(
    current_version: str,
    bump_type: str,
    pre_kind: str = "",
) -> None:
    """Validate that a version bump is legal given the current version state.

    Mirrors the validation rules in :func:`resolve_baseline` so that
    ``uvr bump`` and ``uvr release`` enforce identical invariants.

    Args:
        current_version: Version string from pyproject.toml.
        bump_type: One of "major", "minor", "patch", "alpha", "beta",
            "rc", "post", "dev", "stable".
        pre_kind: PEP 440 short pre-release kind ("a", "b", "rc").
            Required when bump_type is a pre-release name.

    Raises:
        ValueError: If the transition is invalid.
    """
    if bump_type in ("major", "minor", "patch", "dev"):
        return

    v = _parse(strip_dev(current_version))
    has_pre = v.pre is not None
    has_post = v.post is not None

    if bump_type == "stable":
        if has_post or _parse(strip_dev(current_version)).post is not None:
            msg = (
                f"Cannot bump to stable from post-release {current_version} "
                f"— the stable version was already released. "
                f"Use --patch to bump past it."
            )
            raise ValueError(msg)
        return

    if bump_type == "post" and not has_post:
        cv = _parse(current_version)
        # Post is valid from a clean final (released) version.
        # Reject from dev or pre-release versions — those aren't released yet.
        if cv.dev is not None or cv.pre is not None:
            msg = f"Cannot enter post-release from unreleased version {current_version}"
            raise ValueError(msg)

    is_pre_bump = bump_type in ("alpha", "beta", "rc") or pre_kind
    if is_pre_bump and has_post:
        msg = f"Cannot enter pre-release from post-release version {current_version}"
        raise ValueError(msg)

    if is_pre_bump and has_pre and pre_kind:
        current_kind = v.pre[0] if v.pre else ""
        target_order = _PRE_KIND_ORDER.get(pre_kind, -1)
        current_order = _PRE_KIND_ORDER.get(current_kind, -1)
        if target_order < current_order:
            msg = (
                f"Cannot downgrade pre-release kind from "
                f"{current_kind} to {pre_kind} ({current_version})"
            )
            raise ValueError(msg)


# ---------------------------------------------------------------------------
# Release type detection
# ---------------------------------------------------------------------------


def detect_release_type_for_version(version: str) -> str:
    """Detect the release type implied by a single version string.

    Args:
        version: A PEP 440 version string (may include ``.devN``).

    Returns:
        One of ``"stable"``, ``"pre"``, ``"post"``.
        Never returns ``"dev"`` — that is a CLI flag concern.
    """
    v = _parse(version)
    # Look at the non-dev part to determine the release track
    base = _parse(strip_dev(version)) if v.dev is not None else v
    if base.pre is not None:
        return "pre"
    if base.post is not None:
        return "post"
    return "stable"


def detect_release_type(packages: dict) -> str:
    """Auto-detect release type from the first package's version.

    .. deprecated::
        Use :func:`detect_release_type_for_version` per-package instead.
    """
    for info in packages.values():
        return detect_release_type_for_version(info.version)
    return "stable"


# ---------------------------------------------------------------------------
# Version conflicts
# ---------------------------------------------------------------------------


class VersionConflict:
    """A package whose dev version targets an already-released version."""

    def __init__(self, name: str, version: str, release_version: str, tag: str) -> None:
        self.name = name
        self.version = version
        self.release_version = release_version
        self.tag = tag

    def warning(self) -> str:
        return (
            f"{self.name} {self.version} is a dev version for {self.release_version} "
            f"and {self.release_version} was already released (tag: {self.tag})"
        )

    def hint(self) -> str:
        """Suggest a bump command to resolve the conflict."""
        v = _parse(self.release_version)
        if v.pre is not None:
            kind = v.pre[0]
            kind_name = {"a": "alpha", "b": "beta", "rc": "rc"}.get(kind, kind)
            return f"uvr bump --package {self.name} --{kind_name}"
        if v.post is not None:
            return f"uvr bump --package {self.name} --post"
        return f"uvr bump --package {self.name} --patch"


def find_version_conflicts(
    packages: dict,
    repo: object,
) -> list[VersionConflict]:
    """Find packages whose dev version targets an already-released version.

    For example, if version is ``1.0.1a1.dev0`` and the tag
    ``pkg/v1.0.1a1`` already exists, that's a conflict — the version
    was already released and we shouldn't be developing toward it.
    """
    import pygit2

    if not isinstance(repo, pygit2.Repository):
        return []

    conflicts: list[VersionConflict] = []
    for name, info in packages.items():
        v = _parse(info.version)
        if v.dev is None:
            continue
        release_version = strip_dev(info.version)
        tag = f"{name}/v{release_version}"
        if repo.references.get(f"refs/tags/{tag}") is not None:
            conflicts.append(VersionConflict(name, info.version, release_version, tag))
    return conflicts
