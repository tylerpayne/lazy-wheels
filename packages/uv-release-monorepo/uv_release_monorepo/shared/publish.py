"""Publish: generate release notes and create GitHub releases."""

from __future__ import annotations

from collections.abc import Mapping

from packaging.utils import canonicalize_name


from .models import PackageInfo
from pathlib import Path
from .shell import fatal, gh, git, step


def generate_release_notes(
    name: str,
    info: PackageInfo,
    baseline_tag: str | None,
) -> str:
    """Generate markdown release notes for a single package.

    Args:
        name: Package name.
        info: Package metadata (version, path).
        baseline_tag: Git tag to diff from (e.g. "pkg/v1.0.0"), or None.

    Returns:
        Markdown string with release header and commit log.
    """
    lines: list[str] = [f"**Released:** {name} {info.version}"]
    if baseline_tag:
        log = git(
            "log",
            "--oneline",
            f"{baseline_tag}..HEAD",
            "--",
            info.path,
            check=False,
        )
        if log:
            lines += ["", "**Commits:**"]
            for entry in log.splitlines()[:10]:
                lines.append(f"- {entry}")
    return "\n".join(lines)


def publish_release(
    changed: dict[str, PackageInfo],
    release_tags: Mapping[str, str | None],
) -> None:
    """Create one GitHub release per changed package with its wheels attached.

    Each package gets its own release tagged {package}/v{version}, containing
    only that package's wheel(s). Release notes include per-package commit log
    since the last release.

    Args:
        changed: Map of changed package names to PackageInfo.
        release_tags: Most recent release tag per package (for changelog baseline).
    """
    step("Creating GitHub releases")

    for name, info in changed.items():
        release_tag = f"{name}/v{info.version}"
        wheel_name = canonicalize_name(name).replace("-", "_")
        wheels = sorted(
            str(p) for p in Path("dist").glob(f"{wheel_name}-{info.version}-*.whl")
        )
        if not wheels:
            fatal(
                f"No wheels found for {name} {info.version} in dist/. "
                "Ensure build_packages ran successfully."
            )

        notes = generate_release_notes(name, info, release_tags.get(name))

        gh(
            "release",
            "create",
            release_tag,
            *wheels,
            "--title",
            f"{name} {info.version}",
            "--notes",
            notes,
        )
        print(f"  {release_tag} ({len(wheels)} wheels)")
