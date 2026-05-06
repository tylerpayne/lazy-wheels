"""BumpVersions: computed target versions for `uvr version`."""

from __future__ import annotations

from diny import singleton, provider

from ...types.base import Frozen
from ..build.build_packages import BuildPackages
from ..params.bump_type import BumpType
from ..params.version_set import VersionSet
from ...types.version import Version
from ...utils.versioning import compute_bumped_version


@singleton
class BumpVersions(Frozen):
    """Package name -> target version (from --set or --bump)."""

    items: dict[str, Version]


@provider(BumpVersions)
def provide_bump_versions(
    build_packages: BuildPackages,
    bump_type: BumpType,
    version_set: VersionSet,
) -> BumpVersions:
    # --set: all targeted packages get the exact version.
    if version_set.value:
        target = Version.parse(version_set.value)
        return BumpVersions(items={name: target for name in build_packages.items})
    # --bump: compute from current version and bump kind.
    items: dict[str, Version] = {}
    for name, pkg in build_packages.items.items():
        items[name] = compute_bumped_version(pkg.version, bump_type.value)
    return BumpVersions(items=items)
