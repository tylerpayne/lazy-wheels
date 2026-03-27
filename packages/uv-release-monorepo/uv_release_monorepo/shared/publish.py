"""Publish: generate release notes for GitHub releases."""

from __future__ import annotations

import pygit2

from .gitops import commit_log, open_repo
from .models import PackageInfo


def generate_release_notes(
    name: str,
    info: PackageInfo,
    baseline_tag: str | None,
    *,
    repo: pygit2.Repository | None = None,
) -> str:
    """Generate markdown release notes for a single package.

    Args:
        name: Package name.
        info: Package metadata (version, path).
        baseline_tag: Git tag to diff from (e.g. "pkg/v1.0.0"), or None.
        repo: Pre-opened pygit2 Repository. Opened automatically if None.

    Returns:
        Markdown string with release header and commit log.
    """
    lines: list[str] = [f"**Released:** {name} {info.version}"]
    if baseline_tag:
        if repo is None:
            repo = open_repo()
        entries = commit_log(repo, baseline_tag, info.path, limit=10)
        if entries:
            lines += ["", "**Commits:**"]
            for entry in entries:
                lines.append(f"- {entry}")
    return "\n".join(lines)
