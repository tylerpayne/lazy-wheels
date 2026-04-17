"""Pure version computations for the plan step."""

from __future__ import annotations

from ...types import BumpType, Version


def compute_release_version(version: Version, *, dev_release: bool = False) -> Version:
    """Compute the version that will be published."""
    if dev_release:
        # Dev release: publish the .devN version as-is (e.g. 1.0.1.dev3 -> 1.0.1.dev3)
        if version.is_dev:
            return version
        # Non-dev versions cannot be published as dev releases
        msg = f"Cannot do a dev release from non-dev version: {version.raw}"
        raise ValueError(msg)
    # Standard release: strip the dev suffix (e.g. 1.0.1.dev3 -> 1.0.1)
    return version.without_dev() if version.is_dev else version


def compute_next_version(version: Version, *, dev_release: bool = False) -> Version:
    """Compute the post-release dev version."""
    if dev_release:
        # Dev release: increment the dev number (e.g. 1.0.1.dev3 -> 1.0.1.dev4)
        if version.is_dev:
            assert version.dev_number is not None
            return version.with_dev(version.dev_number + 1)
        # Non-dev versions have no dev number to increment
        msg = f"Cannot compute next dev version from non-dev version: {version.raw}"
        raise ValueError(msg)

    # Pre-release: advance to next pre number (e.g. 1.0.1a2 -> 1.0.1a3.dev0)
    if version.pre_kind is not None:
        assert version.pre_number is not None
        return Version.build(
            version.base,
            pre_kind=version.pre_kind,
            pre_number=version.pre_number + 1,
            dev_number=0,
        )
    # Post-release: advance to next post number (e.g. 1.0.1.post2 -> 1.0.1.post3.dev0)
    if version.post_number is not None:
        return Version.build(
            version.base,
            post_number=version.post_number + 1,
            dev_number=0,
        )
    # Stable: bump patch (e.g. 1.0.1 -> 1.0.2.dev0)
    return Version.build(
        f"{version.major}.{version.minor}.{version.patch + 1}", dev_number=0
    )


def compute_bumped_version(version: Version, bump_type: BumpType) -> Version:
    """Compute the version that results from a bump.

    Raises ValueError for invalid transitions.
    """
    match bump_type:
        # Major/minor/patch: reset to new base with .dev0 (e.g. 1.0.1 -> 2.0.0.dev0)
        case BumpType.MAJOR:
            return Version.build(f"{version.major + 1}.0.0", dev_number=0)
        case BumpType.MINOR:
            return Version.build(f"{version.major}.{version.minor + 1}.0", dev_number=0)
        case BumpType.PATCH:
            return Version.build(
                f"{version.major}.{version.minor}.{version.patch + 1}", dev_number=0
            )
        # Stable: strip dev/pre suffixes to finalize (e.g. 1.0.1.dev3 -> 1.0.1)
        case BumpType.STABLE:
            return _bump_stable(version)
        # Dev: increment dev number (e.g. 1.0.1.dev0 -> 1.0.1.dev1)
        case BumpType.DEV:
            return _bump_dev(version)
        # Post: enter post-release track (e.g. 1.0.1 -> 1.0.1.post0.dev0)
        case BumpType.POST:
            return _bump_post(version)
        # Pre-release: enter or advance alpha/beta/rc track
        case BumpType.ALPHA:
            return _bump_pre(version, "a")
        case BumpType.BETA:
            return _bump_pre(version, "b")
        case BumpType.RC:
            return _bump_pre(version, "rc")


def _bump_stable(version: Version) -> Version:
    # Post-release: finalize post number (e.g. 1.0.1.post2.dev0 -> 1.0.1.post2)
    if version.post_number is not None:
        return Version.build(version.base, post_number=version.post_number)
    # Everything else: strip to base (e.g. 1.0.1a2.dev0 -> 1.0.1)
    return Version.build(version.base)


def _bump_dev(version: Version) -> Version:
    # Already dev: increment dev number (e.g. 1.0.1.dev0 -> 1.0.1.dev1)
    if version.dev_number is not None:
        return version.with_dev(version.dev_number + 1)
    # Non-dev: enter dev track (e.g. 1.0.1 -> 1.0.1.dev0)
    return version.with_dev(0)


def _bump_post(version: Version) -> Version:
    # Pre-releases cannot enter the post track
    if version.pre_kind is not None:
        msg = f"Cannot bump post from pre-release: {version.raw}"
        raise ValueError(msg)
    # Already in post track: advance post number (e.g. 1.0.1.post0 -> 1.0.1.post1.dev0)
    if version.post_number is not None:
        return Version.build(
            version.base, post_number=version.post_number + 1, dev_number=0
        )
    # Dev versions cannot enter the post track directly
    if version.is_dev:
        msg = f"Cannot bump post from dev version: {version.raw}"
        raise ValueError(msg)
    # Clean stable: enter post track (e.g. 1.0.1 -> 1.0.1.post0.dev0)
    return Version.build(version.base, post_number=0, dev_number=0)


def _bump_pre(version: Version, target_kind: str) -> Version:
    _PRE_ORDER = {"a": 0, "b": 1, "rc": 2}

    # Post-releases cannot enter a pre-release track
    if version.post_number is not None:
        msg = f"Cannot bump {target_kind} from post-release: {version.raw}"
        raise ValueError(msg)

    current_kind = version.pre_kind
    if current_kind is not None:
        current_rank = _PRE_ORDER.get(current_kind, -1)
        target_rank = _PRE_ORDER[target_kind]
        # Cannot go backwards (e.g. rc -> alpha)
        if target_rank < current_rank:
            msg = f"Cannot go from {current_kind} to {target_kind}: {version.raw}"
            raise ValueError(msg)
        # Same kind: increment pre number (e.g. 1.0.1a2 -> 1.0.1a3.dev0)
        if target_rank == current_rank:
            assert version.pre_number is not None
            return Version.build(
                version.base,
                pre_kind=target_kind,
                pre_number=version.pre_number + 1,
                dev_number=0,
            )
        # Advancing kind: reset to 0 (e.g. 1.0.1a2 -> 1.0.1b0.dev0)
        return Version.build(
            version.base, pre_kind=target_kind, pre_number=0, dev_number=0
        )

    # No current pre-release: enter pre track (e.g. 1.0.1.dev0 -> 1.0.1a0.dev0)
    return Version.build(version.base, pre_kind=target_kind, pre_number=0, dev_number=0)
