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


# ---------------------------------------------------------------------------
# Subtree OID comparison — O(depth) instead of O(files)
# ---------------------------------------------------------------------------


def _resolve_tag(repo: pygit2.Repository, tag_name: str) -> pygit2.Commit | None:
    """Resolve a tag name to its underlying commit."""
    tag_ref = repo.references.get(f"refs/tags/{tag_name}")
    if tag_ref is None:
        return None
    target = repo.get(tag_ref.target)
    if isinstance(target, pygit2.Tag):
        target = repo.get(target.target)
    return target  # type: ignore[return-value]


def _subtree_oid(
    repo: pygit2.Repository, commit: pygit2.Commit, path: str
) -> pygit2.Oid | None:
    """Return the OID of the subtree at *path* in *commit*, or None if absent.

    Walks the tree hierarchy by path components — O(depth), not O(files).
    """
    tree: pygit2.Tree = commit.peel(pygit2.Tree)
    for part in path.rstrip("/").split("/"):
        try:
            entry = tree[part]
        except KeyError:
            return None
        obj = repo.get(entry.id)
        if obj is None:
            return None
        tree = obj  # type: ignore[assignment]
    return tree.id


def path_changed(
    repo: pygit2.Repository,
    old_commit: pygit2.Commit,
    new_commit: pygit2.Commit,
    path: str,
) -> bool:
    """Check if any files under *path* differ between two commits.

    Compares subtree OIDs — O(depth), not O(files in repo).
    """
    return _subtree_oid(repo, old_commit, path) != _subtree_oid(repo, new_commit, path)


def commit_touches_path(
    repo: pygit2.Repository, commit: pygit2.Commit, path: str
) -> bool:
    """Check if *commit* modified any files under *path*.

    Compares the subtree OID between the commit and its first parent.
    O(depth) per commit instead of O(files) full diff.
    """
    if not commit.parents:
        # Root commit — check if path exists
        return _subtree_oid(repo, commit, path) is not None
    return _subtree_oid(repo, commit.parents[0], path) != _subtree_oid(
        repo, commit, path
    )


def commit_log(
    repo: pygit2.Repository,
    tag_name: str,
    path_prefix: str,
) -> list[str]:
    """Return oneline commit messages between *tag_name* and HEAD for *path_prefix*.

    Equivalent to ``git log --oneline <tag>..HEAD -- <path>``.
    Uses subtree OID comparison per commit — O(depth) instead of full diff.
    """
    target = _resolve_tag(repo, tag_name)
    if target is None:
        return []

    head = repo.revparse_single("HEAD")
    walker = repo.walk(head.id, pygit2.GIT_SORT_TIME)  # type: ignore[arg-type]
    walker.hide(target.id)

    entries: list[str] = []
    for commit in walker:
        if commit_touches_path(repo, commit, path_prefix):
            short = str(commit.id)[:7]
            msg = commit.message.split("\n")[0]
            entries.append(f"{short} {msg}")
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
    baseline_version = baseline_tag.split("/v")[-1] if baseline_tag else None
    lines: list[str] = [f"**Released:** {name} {info.version}"]
    if baseline_tag:
        if repo is None:
            repo = open_repo()
        entries = commit_log(repo, baseline_tag, info.path)
        if entries:
            lines += ["", f"**Commits since last release ({baseline_version}):**"]
            for entry in entries:
                lines.append(f"- {entry}")
    return "\n".join(lines)
