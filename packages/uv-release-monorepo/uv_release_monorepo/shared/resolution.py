"""Release resolution state machine.

Given a package's current version and release mode, computes the baseline tag
(for change detection), the release version (to publish), and the next version
(for the post-release bump). Raises structured exceptions on conflicts or
invalid version states.

The version string encodes the state. The release mode (default vs ``--dev``)
is the transition. A dispatch table maps each ``(VersionState, ReleaseMode)``
pair to a handler that computes the three outputs or raises.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from packaging.version import Version as PkgVersion  # noqa: TC002

from .utils.versions import (
    bump_dev,
    bump_patch,
    extract_pre_kind,
    find_release_tags_below,
    is_post,
    is_pre,
    make_dev,
    make_post,
    make_pre,
    strip_dev,
)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


class VersionState(Enum):
    """The 12 distinct version forms a package can be in."""

    CLEAN_STABLE = "X.Y.Z"
    DEV0_STABLE = "X.Y.Z.dev0"
    DEVK_STABLE = "X.Y.Z.devK"
    CLEAN_PRE0 = "X.Y.Za0"
    CLEAN_PREN = "X.Y.ZaN"
    DEV0_PRE = "X.Y.ZaN.dev0"
    DEVK_PRE = "X.Y.ZaN.devK"
    CLEAN_POST0 = "X.Y.Z.post0"
    CLEAN_POSTM = "X.Y.Z.postM"
    DEV0_POST = "X.Y.Z.postM.dev0"
    DEVK_POST = "X.Y.Z.postM.devK"


class ReleaseMode(Enum):
    """How ``uvr release`` was invoked."""

    DEFAULT = "default"
    DEV = "dev"


@dataclass(frozen=True)
class ReleaseResolution:
    """The computed release context for a single package."""

    state: VersionState
    baseline_tag: str | None
    release_version: str
    next_version: str


@dataclass(frozen=True)
class ReleaseConflict:
    """Structured error detail for release resolution failures."""

    kind: str
    name: str
    version: str
    message: str
    hint: str = ""
    tag: str = ""


class ReleaseInvalidError(Exception):
    """The version state is incompatible with the requested release.

    Covers invalid state transitions and missing prerequisites
    (e.g. ``--dev`` without ``.devK`` suffix).
    """

    conflict: ReleaseConflict

    def __init__(self, conflict: ReleaseConflict) -> None:
        self.conflict = conflict
        super().__init__(conflict.message)


class ReleaseConflictError(ReleaseInvalidError):
    """The release would collide with existing tags or versions.

    Covers tag conflicts (release/baseline tags already exist)
    and version conflicts (dev version targeting already-released version).
    """


# ---------------------------------------------------------------------------
# State classification
# ---------------------------------------------------------------------------


def _parse(version_str: str) -> PkgVersion:
    return PkgVersion(version_str)


def classify_version(version: str) -> VersionState:
    """Parse a PEP 440 version string into its state machine state."""
    v = _parse(version)
    has_dev = v.dev is not None
    dev_k = v.dev or 0
    has_pre = _parse(strip_dev(version)).pre is not None
    has_post = v.post is not None
    post_m = v.post or 0

    if has_dev and dev_k > 0:
        if has_post:
            return VersionState.DEVK_POST
        if has_pre:
            return VersionState.DEVK_PRE
        return VersionState.DEVK_STABLE

    if has_dev:  # dev0
        if has_post:
            return VersionState.DEV0_POST
        if has_pre:
            return VersionState.DEV0_PRE
        return VersionState.DEV0_STABLE

    # clean (no .dev)
    if has_post:
        return VersionState.CLEAN_POST0 if post_m == 0 else VersionState.CLEAN_POSTM
    if has_pre:
        pre_n = v.pre[1] if v.pre else 0
        return VersionState.CLEAN_PRE0 if pre_n == 0 else VersionState.CLEAN_PREN
    return VersionState.CLEAN_STABLE


# ---------------------------------------------------------------------------
# Shared conflict checks
# ---------------------------------------------------------------------------


def _check_target_already_released(
    name: str,
    current_version: str,
    release_version: str,
    repo: object,
) -> None:
    """Raise if the version we are developing toward was already published.

    For example, ``1.2.3.dev0`` targets ``1.2.3``. If ``pkg/v1.2.3`` already
    exists, someone needs to bump past it. Only meaningful for dev versions.
    Called exclusively from dev-state handlers.
    """
    tag = f"{name}/v{release_version}"
    if repo.references.get(f"refs/tags/{tag}") is not None:  # type: ignore[union-attr]
        raise ReleaseConflictError(
            ReleaseConflict(
                kind="version_conflict",
                name=name,
                version=current_version,
                tag=tag,
                message=(
                    f"{name} {current_version} targets {release_version} "
                    f"which was already released (tag {tag})"
                ),
                hint=_version_conflict_hint(name, release_version),
            )
        )


def _version_conflict_hint(name: str, release_version: str) -> str:
    v = _parse(release_version)
    if v.pre is not None:
        kind = v.pre[0]
        kind_name = {"a": "alpha", "b": "beta", "rc": "rc"}.get(kind, kind)
        return f"uvr bump --package {name} --{kind_name}"
    if v.post is not None:
        return f"uvr bump --package {name} --post"
    return f"uvr bump --package {name} --patch"


def _check_planned_tags_exist(
    name: str,
    release_version: str,
    next_version: str,
    repo: object,
    skip: frozenset[str],
) -> None:
    """Raise if the tags this release would create already exist.

    Checks the release tag (``pkg/v{release_version}``) and the baseline
    tag (``pkg/v{next_version}-base``). The release tag check is skipped
    when ``uvr-release`` is in the skip set (recovery mode where the tag
    was already created by a prior run).
    """
    check_release = "uvr-release" not in skip
    conflicts: list[str] = []

    if check_release:
        release_tag = f"{name}/v{release_version}"
        if repo.references.get(f"refs/tags/{release_tag}") is not None:  # type: ignore[union-attr]
            conflicts.append(release_tag)

    base_tag = f"{name}/v{next_version}-base"
    if repo.references.get(f"refs/tags/{base_tag}") is not None:  # type: ignore[union-attr]
        conflicts.append(base_tag)

    if not conflicts:
        return

    tags_str = ", ".join(conflicts)
    try:
        bump_ver = make_dev(bump_patch(release_version))
        hint = f"uvr bump --package {name} --patch (to {bump_ver}), or use --post"
    except ValueError:
        hint = "Bump to a new version or use --post"

    raise ReleaseConflictError(
        ReleaseConflict(
            kind="tag_conflict",
            name=name,
            version=release_version,
            tag=conflicts[0],
            message=f"Tag(s) already exist for {name}: {tags_str}",
            hint=hint,
        )
    )


# ---------------------------------------------------------------------------
# Next-version helpers
# ---------------------------------------------------------------------------


def _next_dev_version(release_version: str) -> str:
    """Compute the next dev version after a release.

    Auto-detects from the release version:
    - ``1.0.1``       -> ``1.0.2.dev0``   (stable -> bump patch)
    - ``1.0.1a2``     -> ``1.0.1a3.dev0`` (pre -> increment pre number)
    - ``1.0.1.post0`` -> ``1.0.1.post1.dev0`` (post -> increment post number)
    """
    if is_pre(release_version):
        kind = extract_pre_kind(release_version)
        m = re.search(rf"{re.escape(kind)}(\d+)$", release_version)
        n = int(m.group(1)) + 1 if m else 1
        return make_dev(make_pre(release_version, kind, n))
    if is_post(release_version):
        m = re.search(r"\.post(\d+)$", release_version)
        n = int(m.group(1)) + 1 if m else 1
        return make_dev(make_post(release_version, n))
    return make_dev(bump_patch(release_version))


# ---------------------------------------------------------------------------
# Per-state handlers: clean versions (no .dev)
# ---------------------------------------------------------------------------


def _clean_stable_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.Z + uvr release"""
    baseline_tag = _find_prev_tag(version, name, repo)
    release_version = version
    next_version = _next_dev_version(release_version)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.CLEAN_STABLE,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


def _clean_pre0_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.Za0 + uvr release (first pre-release, needs scan)"""
    baseline_tag = _find_prev_tag(version, name, repo)
    release_version = version
    next_version = _next_dev_version(release_version)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.CLEAN_PRE0,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


def _clean_pren_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.ZaN (N>0) + uvr release (previous is a(N-1))"""
    baseline_tag = _find_prev_tag(version, name, repo)
    release_version = version
    next_version = _next_dev_version(release_version)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.CLEAN_PREN,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


def _clean_post0_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.Z.post0 + uvr release (base version is always X.Y.Z)"""
    from .utils.versions import get_base_version

    baseline_tag = f"{name}/v{get_base_version(version)}"
    release_version = version
    next_version = _next_dev_version(release_version)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.CLEAN_POST0,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


def _clean_postm_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.Z.postM (M>0) + uvr release (previous is post(M-1))"""
    baseline_tag = _find_prev_tag(version, name, repo)
    release_version = version
    next_version = _next_dev_version(release_version)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.CLEAN_POSTM,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


def _find_prev_tag(version: str, name: str, repo: object) -> str | None:
    """Scan tags to find the previous release below the given version."""
    results = find_release_tags_below(version, name, repo, limit=1)
    if not results:
        return None
    return f"{name}/v{results[0]}"


# ---------------------------------------------------------------------------
# Per-state handlers: dev0 versions
# ---------------------------------------------------------------------------


def _dev0_stable_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.Z.dev0 + uvr release"""
    baseline_tag = f"{name}/v{version}-base"
    release_version = strip_dev(version)
    next_version = _next_dev_version(release_version)
    _check_target_already_released(name, version, release_version, repo)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.DEV0_STABLE,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


def _dev0_pre_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.ZaN.dev0 + uvr release (with fallback to stable baseline)"""
    baseline_tag = f"{name}/v{version}-base"
    # Fallback: if the pre-release baseline doesn't exist, try the stable one
    if repo.references.get(f"refs/tags/{baseline_tag}") is None:  # type: ignore[union-attr]
        from .utils.versions import get_base_version

        base = get_base_version(version)
        fallback = f"{name}/v{base}.dev0-base"
        if repo.references.get(f"refs/tags/{fallback}") is not None:  # type: ignore[union-attr]
            baseline_tag = fallback

    release_version = strip_dev(version)
    next_version = _next_dev_version(release_version)
    _check_target_already_released(name, version, release_version, repo)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.DEV0_PRE,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


def _dev0_post_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.Z.postM.dev0 + uvr release"""
    baseline_tag = f"{name}/v{version}-base"
    release_version = strip_dev(version)
    next_version = _next_dev_version(release_version)
    _check_target_already_released(name, version, release_version, repo)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.DEV0_POST,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


# ---------------------------------------------------------------------------
# Per-state handlers: devK > 0 versions (rewind to dev0-base)
# ---------------------------------------------------------------------------


def _devk_stable_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.Z.devK (K>0) + uvr release (rewinds to dev0-base)"""
    baseline_tag = f"{name}/v{strip_dev(version)}.dev0-base"
    release_version = strip_dev(version)
    next_version = _next_dev_version(release_version)
    _check_target_already_released(name, version, release_version, repo)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.DEVK_STABLE,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


def _devk_pre_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.ZaN.devK (K>0) + uvr release (rewinds to aN.dev0-base)"""
    baseline_tag = f"{name}/v{strip_dev(version)}.dev0-base"
    # Fallback to stable baseline if pre-baseline doesn't exist
    if repo.references.get(f"refs/tags/{baseline_tag}") is None:  # type: ignore[union-attr]
        from .utils.versions import get_base_version

        base = get_base_version(version)
        fallback = f"{name}/v{base}.dev0-base"
        if repo.references.get(f"refs/tags/{fallback}") is not None:  # type: ignore[union-attr]
            baseline_tag = fallback

    release_version = strip_dev(version)
    next_version = _next_dev_version(release_version)
    _check_target_already_released(name, version, release_version, repo)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.DEVK_PRE,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


def _devk_post_default(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """X.Y.Z.postM.devK (K>0) + uvr release (rewinds to postM.dev0-base)"""
    baseline_tag = f"{name}/v{strip_dev(version)}.dev0-base"
    release_version = strip_dev(version)
    next_version = _next_dev_version(release_version)
    _check_target_already_released(name, version, release_version, repo)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=VersionState.DEVK_POST,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


# ---------------------------------------------------------------------------
# Per-state handlers: --dev mode
# ---------------------------------------------------------------------------


def _dev_release(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """Any .devK version + uvr release --dev"""
    state = classify_version(version)
    baseline_tag = f"{name}/v{version}-base"
    release_version = version  # publish as-is
    next_version = bump_dev(version)
    _check_target_already_released(name, version, release_version, repo)
    _check_planned_tags_exist(name, release_version, next_version, repo, skip)
    return ReleaseResolution(
        state=state,
        baseline_tag=baseline_tag,
        release_version=release_version,
        next_version=next_version,
    )


def _clean_dev_invalid(
    version: str, name: str, repo: object, skip: frozenset[str]
) -> ReleaseResolution:
    """Any clean version + uvr release --dev (always invalid)"""
    raise ReleaseInvalidError(
        ReleaseConflict(
            kind="dev_required",
            name=name,
            version=version,
            message=(
                f"--dev release requires a .devN version, "
                f"but {name} has clean version {version}"
            ),
            hint=f"uvr bump --package {name} --dev",
        )
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_Handler = Callable[
    [str, str, object, frozenset[str]],
    ReleaseResolution,
]

_TRANSITIONS: dict[tuple[VersionState, ReleaseMode], _Handler] = {
    (VersionState.CLEAN_STABLE, ReleaseMode.DEFAULT): _clean_stable_default,
    (VersionState.CLEAN_STABLE, ReleaseMode.DEV): _clean_dev_invalid,
    (VersionState.DEV0_STABLE, ReleaseMode.DEFAULT): _dev0_stable_default,
    (VersionState.DEV0_STABLE, ReleaseMode.DEV): _dev_release,
    (VersionState.DEVK_STABLE, ReleaseMode.DEFAULT): _devk_stable_default,
    (VersionState.DEVK_STABLE, ReleaseMode.DEV): _dev_release,
    (VersionState.CLEAN_PRE0, ReleaseMode.DEFAULT): _clean_pre0_default,
    (VersionState.CLEAN_PRE0, ReleaseMode.DEV): _clean_dev_invalid,
    (VersionState.CLEAN_PREN, ReleaseMode.DEFAULT): _clean_pren_default,
    (VersionState.CLEAN_PREN, ReleaseMode.DEV): _clean_dev_invalid,
    (VersionState.DEV0_PRE, ReleaseMode.DEFAULT): _dev0_pre_default,
    (VersionState.DEV0_PRE, ReleaseMode.DEV): _dev_release,
    (VersionState.DEVK_PRE, ReleaseMode.DEFAULT): _devk_pre_default,
    (VersionState.DEVK_PRE, ReleaseMode.DEV): _dev_release,
    (VersionState.CLEAN_POST0, ReleaseMode.DEFAULT): _clean_post0_default,
    (VersionState.CLEAN_POST0, ReleaseMode.DEV): _clean_dev_invalid,
    (VersionState.CLEAN_POSTM, ReleaseMode.DEFAULT): _clean_postm_default,
    (VersionState.CLEAN_POSTM, ReleaseMode.DEV): _clean_dev_invalid,
    (VersionState.DEV0_POST, ReleaseMode.DEFAULT): _dev0_post_default,
    (VersionState.DEV0_POST, ReleaseMode.DEV): _dev_release,
    (VersionState.DEVK_POST, ReleaseMode.DEFAULT): _devk_post_default,
    (VersionState.DEVK_POST, ReleaseMode.DEV): _dev_release,
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def resolve_release(
    current_version: str,
    name: str,
    repo: object,
    *,
    dev_release: bool = False,
    skip: frozenset[str] = frozenset(),
) -> ReleaseResolution:
    """Complete release state machine for a single package.

    Given the current version and release mode, computes the baseline tag
    (for change detection), the release version (to publish), and the next
    version (for the post-release bump).

    Raises:
        ReleaseInvalidError: Version state incompatible with the release mode.
        ReleaseConflictError: Planned tags already exist or dev version targets
            an already-released version.
    """
    state = classify_version(current_version)
    mode = ReleaseMode.DEV if dev_release else ReleaseMode.DEFAULT
    handler = _TRANSITIONS[(state, mode)]
    return handler(current_version, name, repo, skip)
