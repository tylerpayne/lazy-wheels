"""Release workflow file state for upgrade/validate intents."""

from __future__ import annotations

import subprocess
from importlib.resources import files
from pathlib import Path

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

    @classmethod
    def parse(cls) -> WorkflowState:
        """Load workflow template, file content, and merge base."""
        root = Path.cwd()
        template = _WORKFLOW_TEMPLATE_PATH.read_text(encoding="utf-8")

        workflow_dir = ".github/workflows"
        rel_dest = f"{workflow_dir}/release.yml"
        dest = root / rel_dest

        file_exists = dest.exists()
        file_content = dest.read_text() if file_exists else ""

        merge_base = _read_base(root, rel_dest)
        has_uncommitted = _has_uncommitted_changes(dest) if file_exists else False

        return WorkflowState(
            template=template,
            file_content=file_content,
            merge_base=merge_base,
            has_uncommitted=has_uncommitted,
            workflow_dir=workflow_dir,
            file_exists=file_exists,
        )


def _read_base(root: Path, rel_path: str) -> str:
    """Read a merge base from .uvr/bases/<rel_path>, or empty string if absent."""
    base_file = root / ".uvr" / "bases" / rel_path
    if base_file.exists():
        return base_file.read_text()
    return ""


def _has_uncommitted_changes(path: Path) -> bool:
    """Check whether a file has uncommitted changes via git diff."""
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", str(path)],
        capture_output=True,
    )
    return result.returncode != 0
