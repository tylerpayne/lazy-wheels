"""UpgradeWorkflowIntent: scaffold or upgrade the release workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..commands import MergeUpgradeCommand, UpdateTomlCommand, WriteFileCommand
from ..states.merge_bases import read_base, resolve_editor
from ..states.templates import load_workflow_template
from ..states.workspace import read_uvr_version
from ..states.worktree import has_uncommitted_changes
from ..types import Command, Job, Plan, Workspace


class UpgradeWorkflowIntent(BaseModel):
    """Intent to scaffold or upgrade the release workflow."""

    model_config = ConfigDict(frozen=True)

    type: Literal["upgrade_workflow"] = "upgrade_workflow"
    workflow_dir: str = ".github/workflows"
    force: bool = False
    upgrade: bool = False
    base_only: bool = False
    editor: str | None = None

    def guard(self, workspace: Workspace) -> None:
        """Check preconditions. Raises ValueError on failure."""
        root = Path.cwd()

        if not (root / ".git").exists():
            msg = "Not a git repository. Run from the repo root."
            raise ValueError(msg)

        if not self.upgrade:
            pyproject = root / "pyproject.toml"
            if not pyproject.exists():
                msg = "No pyproject.toml found."
                raise ValueError(msg)

            dest = root / self.workflow_dir / "release.yml"
            if not self.base_only and dest.exists() and not self.force:
                rel_dest = f"{self.workflow_dir}/release.yml"
                msg = f"{rel_dest} already exists. Use --force to overwrite."
                raise ValueError(msg)

        if self.upgrade:
            dest = root / self.workflow_dir / "release.yml"
            if not dest.exists():
                msg = (
                    f"No workflow found at {self.workflow_dir}/release.yml. "
                    f"Run `uvr workflow init` first."
                )
                raise ValueError(msg)

            if has_uncommitted_changes(dest):
                msg = (
                    f"{self.workflow_dir}/release.yml has uncommitted changes. "
                    f"Commit or stash them first."
                )
                raise ValueError(msg)

    def plan(self, workspace: Workspace) -> Plan:
        """(state, intent) -> plan."""
        root = Path.cwd()
        template_text = load_workflow_template()
        version = read_uvr_version()
        rel_dest = f"{self.workflow_dir}/release.yml"
        dest = root / rel_dest

        commands: list[Command] = []

        if self.base_only:
            commands.append(
                WriteFileCommand(
                    label=f"Write merge base for {rel_dest}",
                    path=str(root / ".uvr" / "bases" / rel_dest),
                    content=template_text,
                )
            )
            return Plan(jobs=[Job(name="upgrade_workflow", commands=commands)])

        if self.upgrade:
            # Three-way merge upgrade
            base_text = read_base(root, rel_dest)
            editor = resolve_editor(self.editor) or ""

            commands.append(
                MergeUpgradeCommand(
                    label=f"Merge upgrade {rel_dest}",
                    dest_path=str(dest),
                    base_text=base_text,
                    fresh_text=template_text,
                    editor=editor,
                )
            )
        else:
            # Fresh init (guard already validated force/exists)
            commands.append(
                WriteFileCommand(
                    label=f"Write {rel_dest}",
                    path=str(dest),
                    content=template_text,
                )
            )

        # Write the merge base
        commands.append(
            WriteFileCommand(
                label=f"Write merge base for {rel_dest}",
                path=str(root / ".uvr" / "bases" / rel_dest),
                content=template_text,
            )
        )

        # Update workflow_version
        commands.append(
            UpdateTomlCommand(
                label=f"Set workflow_version to {version}",
                key="workflow_version",
                value=version,
            )
        )

        return Plan(jobs=[Job(name="upgrade_workflow", commands=commands)])
