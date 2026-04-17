"""Single adapter for all git operations. Wraps pygit2 and git subprocess."""

from __future__ import annotations

import subprocess

import pygit2


class GitRepo:
    """All git I/O goes through this class."""

    def __init__(self, path: str = ".") -> None:
        self._repo = pygit2.Repository(path)

    def find_tag(self, tag_name: str) -> str | None:
        """Return commit SHA for a tag, or None if it doesn't exist."""
        ref = f"refs/tags/{tag_name}"
        if self._repo.references.get(ref) is None:
            return None
        try:
            return str(self._repo.revparse_single(ref).id)
        except (KeyError, AttributeError, pygit2.GitError):
            return None

    def list_tags(self, prefix: str) -> list[str]:
        """List all tag names matching a prefix (without refs/tags/)."""
        full_prefix = f"refs/tags/{prefix}"
        result: list[str] = []
        try:
            for ref in self._repo.listall_references():
                if ref.startswith(full_prefix):
                    result.append(ref[len("refs/tags/") :])
        except (AttributeError, OSError):
            pass
        return result

    def path_changed(self, from_commit: str, to_commit: str, path: str) -> bool:
        """Check if a path changed between two commits by comparing tree OIDs."""
        try:
            from_tree = self._repo.revparse_single(from_commit).peel(pygit2.Tree)
            to_tree = self._repo.revparse_single(to_commit).peel(pygit2.Tree)
        except (KeyError, AttributeError):
            return True

        try:
            from_oid = from_tree[path].id
        except KeyError:
            return True

        try:
            to_oid = to_tree[path].id
        except KeyError:
            return True

        return from_oid != to_oid

    def commit_log(self, from_commit: str, to_commit: str, path: str) -> str:
        """Return oneline commit log between two commits for a path."""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", f"{from_commit}..{to_commit}", "--", path],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    def diff_stats(self, from_commit: str, to_commit: str, path: str) -> str | None:
        """Return diff stat summary between two commits for a path."""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", f"{from_commit}..{to_commit}", "--", path],
                capture_output=True,
                text=True,
                check=False,
            )
            output = result.stdout.strip()
            return output if result.returncode == 0 and output else None
        except (OSError, subprocess.SubprocessError):
            return None

    def create_tag(self, tag_name: str, target: str = "HEAD") -> None:
        """Create a lightweight git tag pointing at the given target."""
        obj = self._repo.revparse_single(target)
        self._repo.create_reference(f"refs/tags/{tag_name}", obj.id)

    def head_commit(self) -> str:
        """Return HEAD commit SHA."""
        return str(self._repo.revparse_single("HEAD").id)

    def is_dirty(self) -> bool:
        """Return True if the working tree has uncommitted changes."""
        status = self._repo.status()
        return len(status) > 0

    def is_ahead_or_behind(self) -> bool:
        """Return True if HEAD differs from its upstream tracking branch."""
        head = self._repo.head
        branch = self._repo.branches.get(head.shorthand)
        if branch is None:
            return False
        upstream = branch.upstream
        if upstream is None:
            return False
        local_oid = branch.target
        remote_oid = upstream.target
        return local_oid != remote_oid
