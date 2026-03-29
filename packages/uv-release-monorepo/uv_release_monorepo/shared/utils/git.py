"""Local git operations using pygit2 (no subprocess overhead)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygit2

if TYPE_CHECKING:
    from ..models import PackageInfo


def open_repo(path: str = ".") -> pygit2.Repository:
    """Open the git repository at *path*."""
    return pygit2.Repository(path)


def list_tags(
    repo: pygit2.Repository, *, prefixes: list[str] | None = None
) -> list[str]:
    """Return tag names (without ``refs/tags/`` prefix).

    If *prefixes* is given, only return tags starting with one of
    the prefixes (e.g. ``["pkg-alpha/v", "pkg-beta/v"]``).
    """
    ref_prefix = "refs/tags/"
    plen = len(ref_prefix)
    tags = [r[plen:] for r in repo.listall_references() if r.startswith(ref_prefix)]
    if prefixes:
        tags = [t for t in tags if any(t.startswith(p) for p in prefixes)]
    return tags


def diff_files(repo: pygit2.Repository, tag_name: str) -> set[str]:
    """Return file paths changed between *tag_name* and HEAD."""
    tag_ref = repo.references.get(f"refs/tags/{tag_name}")
    if tag_ref is None:
        return set()
    target = repo.get(tag_ref.target)
    # Peel annotated tags to the underlying commit
    if isinstance(target, pygit2.Tag):
        target = repo.get(target.target)
    head = repo.revparse_single("HEAD")
    diff: pygit2.Diff = repo.diff(target, head)  # type: ignore[arg-type]
    return {patch.delta.new_file.path or patch.delta.old_file.path for patch in diff}


def commit_log(
    repo: pygit2.Repository,
    tag_name: str,
    path_prefix: str,
    limit: int = 10,
) -> list[str]:
    """Return oneline commit messages between *tag_name* and HEAD for *path_prefix*.

    Equivalent to ``git log --oneline <tag>..HEAD -- <path>``.
    """
    tag_ref = repo.references.get(f"refs/tags/{tag_name}")
    if tag_ref is None:
        return []
    target = repo.get(tag_ref.target)
    if isinstance(target, pygit2.Tag):
        target = repo.get(target.target)
    if target is None:
        return []

    head = repo.revparse_single("HEAD")
    walker = repo.walk(head.id, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]
    walker.hide(target.id)

    entries: list[str] = []
    for commit in walker:
        if not commit.parents:
            continue
        diff: pygit2.Diff = repo.diff(commit.parents[0], commit)
        for patch in diff:
            if patch is None:
                continue
            p = patch.delta.new_file.path
            if p and p.startswith(path_prefix):
                short = str(commit.id)[:7]
                msg = commit.message.split("\n")[0]
                entries.append(f"{short} {msg}")
                break
        if len(entries) >= limit:
            break
    return entries


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
