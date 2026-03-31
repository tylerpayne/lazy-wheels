"""Version parsing and bumping utilities.

Handles conversion between version strings and semver objects, with
special handling for incomplete version strings (e.g., "1.0" -> "1.0.0")
and PEP 440 dev/pre/post versions.
"""

from __future__ import annotations

import re

import semver

_DEV_RE = re.compile(r"\.dev\d*$")
_DEV_NUM_RE = re.compile(r"\.dev(\d+)$")


def strip_dev(version_str: str) -> str:
    """Remove a PEP 440 ``.devN`` suffix if present.

    Examples:
        "1.2.3.dev0" -> "1.2.3"
        "1.2.3" -> "1.2.3"
        "1.2.3.post0.dev0" -> "1.2.3.post0"
    """
    return _DEV_RE.sub("", version_str)


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
    m = _DEV_NUM_RE.search(version_str)
    if m:
        n = int(m.group(1))
        return version_str[: m.start()] + f".dev{n + 1}"
    return f"{version_str}.dev0"


def is_dev(version_str: str) -> bool:
    """Check if a version has a .devN suffix."""
    return _DEV_RE.search(version_str) is not None


_PRE_RE = re.compile(r"(a|b|rc)\d+")


def is_pre(version_str: str) -> bool:
    """Check if a version has an alpha, beta, or rc suffix."""
    return _PRE_RE.search(version_str) is not None


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
        v = _DEV_RE.sub("", v)
    if post:
        v = re.sub(r"\.post\d+$", "", v)
    if pre:
        v = re.sub(r"(a|b|rc)\d+$", "", v)
    return v


def get_base_version(version_str: str) -> str:
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
    return f"{get_base_version(version_str)}{kind}{n}"


def make_post(version_str: str, n: int = 0) -> str:
    """Create a post-release version.

    Args:
        version_str: Must be a final release version.
        n: Post-release number (default 0).

    Examples:
        make_post("1.2.3") -> "1.2.3.post0"
        make_post("1.2.3", 1) -> "1.2.3.post1"
    """
    return f"{get_base_version(version_str)}.post{n}"


_PRE_KINDS = ("rc", "b", "a")  # ordered high to low for kind chain
_PRE_KIND_ORDER = {"a": 0, "b": 1, "rc": 2}  # ordered low to high for comparison
_PRE_KIND_RE = re.compile(r"(a|b|rc)\d+")


def extract_pre_kind(version_str: str) -> str:
    """Extract the pre-release kind (a, b, rc) from a version string.

    Returns an empty string if no pre-release suffix is present.

    Examples:
        "1.2.3a1" -> "a"
        "1.2.3b0.dev0" -> "b"
        "1.2.3rc2" -> "rc"
        "1.2.3.dev0" -> ""
    """
    m = _PRE_KIND_RE.search(version_str)
    return m.group(1) if m else ""


def find_previous_release(
    version_str: str,
    name: str,
    repo: object,
) -> str | None:
    """Derive the previous release version from any version string.

    Works with both dev versions (1.0.1.dev0) and clean versions (1.0.1b0).
    Uses O(1) ref lookups for common cases, narrow globs for minor/major bumps.

    Args:
        version_str: Current version (with or without .devN suffix).
        name: Package name for tag prefix.
        repo: pygit2.Repository for ref lookups.

    Returns:
        The previous release version string, or None if not found.

    Raises:
        ValueError: If version resolves to 0.0.0 (no possible previous).

    Examples:
        Dev versions:
        "1.0.1.dev3"       → "1.0.1.dev2"
        "1.0.1.dev0"       → "1.0.0"
        "1.0.1a1.dev0"     → "1.0.1a0"
        "1.0.1a0.dev0"     → "1.0.0"

        Clean versions:
        "1.0.1b0"          → highest a* tag (kind chain)
        "1.0.1rc0"         → highest b* tag, else highest a*
        "1.0.1a0"          → "1.0.0" (previous final)
        "1.0.1"            → "1.0.0"
        "1.0.1.post0"      → "1.0.1"
    """

    def _tag_exists(ver: str) -> bool:
        return repo.references.get(f"refs/tags/{name}/v{ver}") is not None  # type: ignore[union-attr]

    def _glob_highest(prefix: str) -> str | None:
        """Find highest version matching a tag prefix.

        Uses filesystem glob on .git/refs/tags/ when available (fast),
        falls back to pygit2 ref scan for packed refs or mock repos.
        """
        from pathlib import Path

        candidates = []

        # Fast path: filesystem glob
        try:
            tag_dir = Path(repo.path) / "refs" / "tags" / name  # type: ignore[union-attr]
            if tag_dir.is_dir():
                for path in tag_dir.glob(f"v{prefix}*"):
                    if path.name.endswith("-base"):
                        continue
                    ver_str = path.name[1:]  # strip leading "v"
                    try:
                        candidates.append((parse_version(ver_str), ver_str))
                    except (ValueError, TypeError):
                        continue
        except (AttributeError, OSError):
            pass

        # Fallback: pygit2 ref scan (for packed refs or mocks)
        if not candidates:
            ref_prefix = f"refs/tags/{name}/v{prefix}"
            for ref in repo.listall_references():  # type: ignore[union-attr]
                if ref.startswith(ref_prefix) and not ref.endswith("-base"):
                    ver_str = ref.split("/v")[-1]
                    try:
                        candidates.append((parse_version(ver_str), ver_str))
                    except (ValueError, TypeError):
                        continue

        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    # Step 1: Handle .devN suffix
    dev_m = _DEV_NUM_RE.search(version_str)
    if dev_m:
        dev_n = int(dev_m.group(1))
        if dev_n > 0:
            # 1a: dev N > 0 → previous dev
            prev = strip_dev(version_str) + f".dev{dev_n - 1}"
            if _tag_exists(prev):
                return prev
            return None
        # 1b: dev 0 → strip .dev0, fall through to clean version rules
        clean = strip_dev(version_str)
    else:
        clean = version_str

    # Step 2: Pre-release suffix (a/b/rc)
    pre_m = re.search(r"(a|b|rc)(\d+)$", clean)
    if pre_m:
        kind = pre_m.group(1)
        pre_n = int(pre_m.group(2))
        base_prefix = clean[: pre_m.start()]

        if pre_n > 0:
            # 2a: pre N > 0 → decrement same kind
            prev = f"{base_prefix}{kind}{pre_n - 1}"
            if _tag_exists(prev):
                return prev

        # 2b: pre N == 0 (or N-1 not found) → walk down kind chain
        kind_idx = _PRE_KINDS.index(kind) if kind in _PRE_KINDS else -1
        for lower_kind in _PRE_KINDS[kind_idx + 1 :]:
            found = _glob_highest(f"{base_prefix}{lower_kind}")
            if found:
                return found

        # No lower pre-release found → fall through to plain X.Y.Z

    # Step 3: Post-release suffix
    post_m = re.search(r"\.post(\d+)$", clean)
    if post_m:
        post_n = int(post_m.group(1))
        if post_n > 0:
            # 3a: post N > 0 → decrement post
            prev = f"{clean[: post_m.start()]}.post{post_n - 1}"
            if _tag_exists(prev):
                return prev
        # 3b: post 0 → the final it patches
        prev = clean[: post_m.start()]
        if _tag_exists(prev):
            return prev
        return None

    # Step 4: Plain X.Y.Z
    base = get_base_version(clean)
    sv = parse_version(base)

    # 4a: patch > 0 → decrement patch
    if sv.patch > 0:
        prev = f"{sv.major}.{sv.minor}.{sv.patch - 1}"
        if _tag_exists(prev):
            return prev

    # 4b: minor > 0 → glob X.{Y-1}.*
    if sv.minor > 0:
        return _glob_highest(f"{sv.major}.{sv.minor - 1}.")

    # 4c: major > 0 → glob {X-1}.*
    if sv.major > 0:
        return _glob_highest(f"{sv.major - 1}.")

    # 4d: 0.0.0 — no previous release possible
    msg = f"Cannot determine previous release for {version_str} — version is 0.0.0"
    raise ValueError(msg)


_POST_RE = re.compile(r"\.post\d+")


def is_post(version_str: str) -> bool:
    """Check if a version has a .postN suffix (ignoring any trailing .devN)."""
    return _POST_RE.search(strip_dev(version_str)) is not None


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
    has_dev = is_dev(current_version)
    has_pre = is_pre(strip_dev(current_version))
    has_post = is_post(current_version)

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
        dev_m = _DEV_NUM_RE.search(current_version)
        if dev_m and int(dev_m.group(1)) > 0:
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
        dev_m = _DEV_NUM_RE.search(current_version)
        if dev_m and int(dev_m.group(1)) > 0:
            # devN (N > 0) → rewind to dev0-base
            return f"{name}/v{strip_dev(current_version)}.dev0-base"
        return f"{name}/v{current_version}-base"

    # Final dev (X.X.X.devN) + non-dev release → use dev0 baseline
    dev_m = _DEV_NUM_RE.search(current_version)
    if dev_m and int(dev_m.group(1)) > 0:
        # devN (N > 0) → rewind to dev0-base
        return f"{name}/v{strip_dev(current_version)}.dev0-base"

    # dev0 → current baseline
    return f"{name}/v{current_version}-base"


def parse_tag_version(tag: str) -> str:
    """Extract the version string from a release tag.

    Tags follow the pattern ``{package-name}/v{version}``.

    Examples:
        "pkg/v1.0.0" -> "1.0.0"
        "my-pkg/v2.3.4.dev0" -> "2.3.4.dev0"
    """
    return tag.split("/v")[-1]


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
    cleaned = get_base_version(version_str)
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
            "rc", "post", "dev".
        pre_kind: PEP 440 short pre-release kind ("a", "b", "rc").
            Required when bump_type is a pre-release name.

    Raises:
        ValueError: If the transition is invalid.
    """
    if bump_type in ("major", "minor", "patch", "dev"):
        return

    has_pre = is_pre(strip_dev(current_version))
    has_post = is_post(current_version)

    if bump_type == "post" and not has_post:
        msg = f"Cannot enter post-release from unreleased version {current_version}"
        raise ValueError(msg)

    is_pre_bump = bump_type in ("alpha", "beta", "rc") or pre_kind
    if is_pre_bump and has_post:
        msg = f"Cannot enter pre-release from post-release version {current_version}"
        raise ValueError(msg)

    if is_pre_bump and has_pre and pre_kind:
        current_kind = extract_pre_kind(strip_dev(current_version))
        target_order = _PRE_KIND_ORDER.get(pre_kind, -1)
        current_order = _PRE_KIND_ORDER.get(current_kind, -1)
        if target_order < current_order:
            msg = (
                f"Cannot downgrade pre-release kind from "
                f"{current_kind} to {pre_kind} ({current_version})"
            )
            raise ValueError(msg)


def detect_release_type(packages: dict) -> str:
    """Auto-detect release type from package versions.

    Examines the first package's version to determine what kind of release
    the user is working toward, so baselines resolve correctly.

    Returns one of ``"stable"``, ``"pre"``, ``"post"``.
    """
    for info in packages.values():
        v = info.version
        if is_dev(v):
            base = v.rsplit(".dev", 1)[0]
            if is_pre(base):
                return "pre"
            if is_post(base):
                return "post"
            return "stable"
        if is_pre(v):
            return "pre"
        if is_post(v):
            return "post"
        return "stable"
    return "stable"


def find_version_conflicts(
    packages: dict,
    repo: object,
) -> list[str]:
    """Find packages whose dev version targets an already-released version.

    For example, if version is ``1.0.1a1.dev0`` and the tag
    ``pkg/v1.0.1a1`` already exists, that's a conflict — the version
    was already released and we shouldn't be developing toward it.

    Returns a list of human-readable warning strings.
    """
    import pygit2

    if not isinstance(repo, pygit2.Repository):
        return []

    warnings: list[str] = []
    for name, info in packages.items():
        v = info.version
        if not is_dev(v):
            continue
        release_version = strip_dev(v)
        tag = f"{name}/v{release_version}"
        if repo.references.get(f"refs/tags/{tag}") is not None:
            warnings.append(
                f"{name} {v} targets {release_version} which was already released "
                f"(tag: {tag})"
            )
    return warnings
