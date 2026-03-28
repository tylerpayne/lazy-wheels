"""Git operations: local (pygit2) and remote (GitHub API)."""

from .local import (
    commit_log,
    diff_files,
    generate_release_notes,
    list_tags,
    open_repo,
)
from .remote import list_release_tag_names

__all__ = [
    "commit_log",
    "diff_files",
    "generate_release_notes",
    "list_release_tag_names",
    "list_tags",
    "open_repo",
]
