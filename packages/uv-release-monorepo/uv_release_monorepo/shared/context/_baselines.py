"""Baseline tag discovery: derive baseline tags from package versions."""

from __future__ import annotations

from ..models import PackageInfo
from ..shell import print_step


def find_baselines(
    packages: dict[str, PackageInfo],
    all_tags: set[str],
) -> dict[str, str | None]:
    """Derive baseline tags from each package's pyproject.toml version.

    The baseline tag is ``{name}/v{version}-base`` where *version* comes from
    pyproject.toml. If the tag does not exist, returns None for that package.

    Args:
        packages: Map of package name -> PackageInfo.
        all_tags: Set of all git tag names.

    Returns:
        Map of package name to its baseline tag, or None if no tag exists.
    """
    print_step("Finding baselines")

    baselines: dict[str, str | None] = {}
    for name, info in packages.items():
        base_tag = f"{name}/v{info.version}-base"
        baselines[name] = base_tag if base_tag in all_tags else None
        print(f"  {name}: {baselines[name] or '<none>'}")

    return baselines
