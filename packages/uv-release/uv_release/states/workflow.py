"""Release workflow file state for upgrade/validate intents."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from diny import provider

from ..utils.git import GitRepo
from .shared.merge_bases import read_merge_base
from .base import State

_WORKFLOW_TEMPLATE_PATH = files("uv_release").joinpath("templates/release/release.yml")


class WorkflowState(State):
    """Release workflow file state for upgrade/validate intents."""

    template: str = ""
    file_content: str = ""
    merge_base: str = ""
    has_uncommitted: bool = False
    workflow_dir: str = ".github/workflows"
    file_exists: bool = False


@provider(WorkflowState)
def parse_workflow_state(git_repo: GitRepo) -> WorkflowState:
    """Load workflow template, file content, and merge base."""
    root = Path.cwd()
    template = _WORKFLOW_TEMPLATE_PATH.read_text(encoding="utf-8")

    workflow_dir = ".github/workflows"
    rel_dest = f"{workflow_dir}/release.yml"
    dest = root / rel_dest

    file_exists = dest.exists()
    file_content = dest.read_text() if file_exists else ""

    merge_base = read_merge_base(root, rel_dest)
    uncommitted = git_repo.file_is_dirty(str(dest)) if file_exists else False

    return WorkflowState(
        template=template,
        file_content=file_content,
        merge_base=merge_base,
        has_uncommitted=uncommitted,
        workflow_dir=workflow_dir,
        file_exists=file_exists,
    )
