"""Pure version computations. No DI, no I/O."""

from __future__ import annotations

from ..types.bump_kind import BumpKind
from ..types.package import Package
from ..types.pin import Pin
from ..types.version import Version


def compute_release_version(version: Version, *, dev_release: bool = False) -> Version:
    """Compute the version that will be published.

    PyPI rejects local version identifiers, so they are always stripped here
    regardless of dev_release mode.
    """
    cleaned = version.without_local() if version.local is not None else version
    if dev_release:
        if cleaned.is_dev:
            return cleaned
        msg = f"Cannot do a dev release from non-dev version: {version.raw}"
        raise ValueError(msg)
    return cleaned.without_dev() if cleaned.is_dev else cleaned


def compute_next_version(version: Version, *, dev_release: bool = False) -> Version:
    """Compute the post-release dev version."""
    if dev_release:
        if version.is_dev:
            assert version.dev_number is not None
            return version.with_dev(version.dev_number + 1)
        msg = f"Cannot compute next dev version from non-dev version: {version.raw}"
        raise ValueError(msg)

    # Pre-release: advance within the same kind.
    if version.pre_kind is not None:
        assert version.pre_number is not None
        return Version.build(
            version.base,
            pre_kind=version.pre_kind,
            pre_number=version.pre_number + 1,
            dev_number=0,
        )
    # Post-release: advance post counter.
    if version.post_number is not None:
        return Version.build(
            version.base,
            post_number=version.post_number + 1,
            dev_number=0,
        )
    # Stable: advance patch.
    return Version.build(
        f"{version.major}.{version.minor}.{version.patch + 1}", dev_number=0
    )


def compute_bumped_version(version: Version, bump_kind: BumpKind) -> Version:
    """Compute the version that results from a bump."""
    if version.local is not None:
        msg = (
            f"Cannot bump version with local segment: {version.raw}. "
            "Strip the local segment first (set the version explicitly)."
        )
        raise ValueError(msg)
    match bump_kind:
        case BumpKind.MAJOR:
            return Version.build(f"{version.major + 1}.0.0", dev_number=0)
        case BumpKind.MINOR:
            return Version.build(f"{version.major}.{version.minor + 1}.0", dev_number=0)
        case BumpKind.PATCH:
            return Version.build(
                f"{version.major}.{version.minor}.{version.patch + 1}", dev_number=0
            )
        case BumpKind.STABLE:
            # Strip dev/pre suffix; keep post number if present.
            if version.post_number is not None:
                return Version.build(version.base, post_number=version.post_number)
            return Version.build(version.base)
        case BumpKind.DEV:
            if version.dev_number is not None:
                return version.with_dev(version.dev_number + 1)
            return version.with_dev(0)
        case BumpKind.POST:
            # POST only valid on stable/post-release versions.
            if version.pre_kind is not None:
                msg = f"Cannot bump post from pre-release: {version.raw}"
                raise ValueError(msg)
            if version.post_number is not None:
                return Version.build(
                    version.base, post_number=version.post_number + 1, dev_number=0
                )
            if version.is_dev:
                msg = f"Cannot bump post from dev version: {version.raw}"
                raise ValueError(msg)
            return Version.build(version.base, post_number=0, dev_number=0)
        case BumpKind.ALPHA:
            return _bump_pre(version, "a")
        case BumpKind.BETA:
            return _bump_pre(version, "b")
        case BumpKind.RC:
            return _bump_pre(version, "rc")
        case BumpKind.PROMOTE:
            return _promote(version)
        case BumpKind.AUTO:
            return _auto_bump(version)


def _promote(version: Version) -> Version:
    """Advance to the next release stage.

    dev -> alpha    (0.1.0.dev3 -> 0.1.0a0.dev0)
    alpha -> beta   (0.1.0a2 -> 0.1.0b0.dev0, 0.1.0a2.dev0 -> 0.1.0b0.dev0)
    beta -> rc      (0.1.0b1 -> 0.1.0rc0.dev0)
    rc -> final     (0.1.0rc1 -> 0.1.0)
    """
    # Check pre-release kind first so that dev-suffixed pre-releases
    # (e.g. 0.1.0a2.dev0) promote by stage, not by stripping dev.
    if version.pre_kind == "a":
        return Version.build(version.base, pre_kind="b", pre_number=0, dev_number=0)
    if version.pre_kind == "b":
        return Version.build(version.base, pre_kind="rc", pre_number=0, dev_number=0)
    if version.pre_kind == "rc":
        return Version.build(version.base)
    # Pure dev version (no pre-release): advance to alpha.
    if version.is_dev:
        return Version.build(version.base, pre_kind="a", pre_number=0, dev_number=0)
    if version.post_number is not None:
        msg = f"Cannot promote post-release {version.raw}. Bump first, then promote."
        raise ValueError(msg)
    msg = f"Cannot promote: {version.raw} is already a final release"
    raise ValueError(msg)


def _auto_bump(version: Version) -> Version:
    """Increment the last section's number in place.

    dev suffix present: increment dev number (1.0.0a2.dev0 -> 1.0.0a2.dev1)
    post release:       increment post number (1.0.0.post1 -> 1.0.0.post2)
    pre-release:        increment pre number  (1.0.0a2 -> 1.0.0a3)
    clean stable:       increment patch        (1.0.0 -> 1.0.1)
    """
    if version.is_dev:
        assert version.dev_number is not None
        return version.with_dev(version.dev_number + 1)
    if version.post_number is not None:
        return Version.build(version.base, post_number=version.post_number + 1)
    if version.pre_kind is not None:
        assert version.pre_number is not None
        return Version.build(
            version.base, pre_kind=version.pre_kind, pre_number=version.pre_number + 1
        )
    return Version.build(f"{version.major}.{version.minor}.{version.patch + 1}")


def _bump_pre(version: Version, target_kind: str) -> Version:
    # Rank order: a < b < rc. Regression (e.g. rc -> a) is forbidden.
    _PRE_ORDER = {"a": 0, "b": 1, "rc": 2}

    if version.post_number is not None:
        msg = f"Cannot bump {target_kind} from post-release: {version.raw}"
        raise ValueError(msg)

    current_kind = version.pre_kind
    if current_kind is not None:
        current_rank = _PRE_ORDER.get(current_kind, -1)
        target_rank = _PRE_ORDER[target_kind]
        if target_rank < current_rank:
            msg = f"Cannot go from {current_kind} to {target_kind}: {version.raw}"
            raise ValueError(msg)
        if target_rank == current_rank:
            assert version.pre_number is not None
            return Version.build(
                version.base,
                pre_kind=target_kind,
                pre_number=version.pre_number + 1,
                dev_number=0,
            )
        # Higher kind: reset pre number to 0.
        return Version.build(
            version.base, pre_kind=target_kind, pre_number=0, dev_number=0
        )

    # No existing pre: start from 0.
    return Version.build(version.base, pre_kind=target_kind, pre_number=0, dev_number=0)


def compute_dependency_pins(
    new_versions: dict[str, Version],
    all_packages: dict[str, Package],
) -> list[Pin]:
    """Compute dependency pins for packages whose deps are being bumped.

    For each package in all_packages, if any of its internal deps are in
    new_versions, generate a Pin with the new version range. Dev versions
    are skipped because they are not installable from PyPI without --pre.
    """
    bumped_names = set(new_versions.keys())
    pins: list[Pin] = []

    for pkg in all_packages.values():
        pkg_pins: dict[str, str] = {}
        for dep in pkg.dep_names:
            if dep in bumped_names:
                nv = new_versions[dep]
                # Never pin to dev versions. They are not installable from PyPI.
                if nv.is_dev:
                    continue
                lower = nv.raw
                upper = f"{nv.major}.{nv.minor + 1}.0"
                pkg_pins[dep] = f"{dep}>={lower},<{upper}"
        if pkg_pins:
            pins.append(Pin(package_path=pkg.path, pins=pkg_pins))

    return pins
