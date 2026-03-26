"""Build: fetch unchanged wheels and build changed packages."""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from pathlib import Path

from packaging.utils import canonicalize_name


from .graph import topo_sort
from .models import PackageInfo
from .shell import fatal, run, step
from .versions import version_from_tag


def fetch_unchanged_wheels(
    unchanged: dict[str, PackageInfo],
    release_tags: Mapping[str, str | None],
) -> None:
    """Download wheels for unchanged packages from their per-package GitHub releases.

    Each package has its own GitHub release tagged {package}/v{version}. This
    function downloads the wheel for each unchanged package directly from its
    release, avoiding a full scan of all releases.

    Args:
        unchanged: Map of unchanged package names to PackageInfo.
        release_tags: Map of package name to last release tag (e.g. "pkg/v1.2.3").
    """
    if not unchanged:
        return

    step("Fetching unchanged wheels from releases")

    for name in unchanged:
        tag = release_tags.get(name)
        if not tag:
            warnings.warn(
                f"no release tag for {name}, skipping wheel fetch",
                UserWarning,
                stacklevel=2,
            )
            continue

        wheel_name = canonicalize_name(name).replace("-", "_")
        result = run(
            "gh",
            "release",
            "download",
            tag,
            "--pattern",
            f"{wheel_name}-*.whl",
            "--dir",
            "dist/",
            "--clobber",
            check=False,
        )
        if result.returncode != 0:
            warnings.warn(
                f"could not download wheel for {name} from {tag}",
                UserWarning,
                stacklevel=2,
            )
            continue

        # Find what was downloaded and report it
        released_version = version_from_tag(tag) if "/v" in tag else ""
        found = list(Path("dist").glob(f"{wheel_name}-{released_version}-*.whl"))
        if found:
            print(f"  Reusing: {found[0].name}")
        else:
            warnings.warn(
                f"no wheel found for {name} after downloading {tag}",
                UserWarning,
                stacklevel=2,
            )


def build_packages(changed: dict[str, PackageInfo]) -> None:
    """Build wheels for the specified packages using uv build.

    Packages are built in topological order so dependencies are built
    before the packages that depend on them.
    """
    step(f"Building {len(changed)} packages")

    # Build in dependency order. topo_sort is correct here because builds
    # run sequentially within a single runner. topo_layers is used for
    # display purposes only (showing parallelism in the plan summary).
    build_order = topo_sort(changed)
    for pkg in build_order:
        info = changed[pkg]
        print(f"\n  {pkg} ({info.path})")
        result = run(
            "uv",
            "build",
            info.path,
            "--out-dir",
            "dist/",
            "--find-links",
            "dist/",
            check=False,
        )
        if result.returncode != 0:
            fatal(f"Failed to build {pkg}. Check uv build output above for details.")
