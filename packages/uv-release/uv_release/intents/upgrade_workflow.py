"""UpgradeWorkflowIntent: scaffold or upgrade the release workflow."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..commands import MergeUpgradeCommand, UpdateTomlCommand, WriteFileCommand
from ..states.uvr_state import UvrState
from ..states.workflow import WorkflowState
from ..states.workspace import Workspace
from ..types import Command, Job, Plan


class UpgradeWorkflowIntent(BaseModel):
    """Intent to scaffold or upgrade the release workflow."""

    model_config = ConfigDict(frozen=True)

    type: Literal["upgrade_workflow"] = "upgrade_workflow"
    workflow_dir: str = ".github/workflows"
    force: bool = False
    upgrade: bool = False
    base_only: bool = False
    editor: str | None = None

    def guard(self, *, workspace: Workspace, workflow_state: WorkflowState) -> None:
        """Check preconditions. Raises ValueError on failure."""
        if not self.upgrade:
            if not self.base_only and workflow_state.file_exists and not self.force:
                rel_dest = f"{self.workflow_dir}/release.yml"
                msg = f"{rel_dest} already exists. Use --force to overwrite."
                raise ValueError(msg)

        if self.upgrade:
            if not workflow_state.file_exists:
                msg = (
                    f"No workflow found at {self.workflow_dir}/release.yml. "
                    f"Run `uvr workflow init` first."
                )
                raise ValueError(msg)

            if workflow_state.has_uncommitted:
                msg = (
                    f"{self.workflow_dir}/release.yml has uncommitted changes. "
                    f"Commit or stash them first."
                )
                raise ValueError(msg)

    def plan(
        self,
        *,
        workspace: Workspace,
        uvr_state: UvrState,
        workflow_state: WorkflowState,
    ) -> Plan:
        """(state, intent) -> plan."""
        root = workspace.root
        template_text = workflow_state.template
        version = uvr_state.uvr_version
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
            base_text = workflow_state.merge_base
            editor = uvr_state.editor or ""

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
