"""UpgradeSkillIntent: scaffold or upgrade Claude Code skill files."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..commands import MergeUpgradeCommand, UpdateTomlCommand, WriteFileCommand
from ..states.skill import SkillState
from ..states.uvr_state import UvrState
from ..states.workspace import Workspace
from ..types import Command, Job, Plan


class UpgradeSkillIntent(BaseModel):
    """Intent to scaffold or upgrade Claude Code skill files."""

    model_config = ConfigDict(frozen=True)

    type: Literal["upgrade_skill"] = "upgrade_skill"
    force: bool = False
    upgrade: bool = False
    base_only: bool = False
    editor: str | None = None

    def guard(self, *, workspace: Workspace) -> None:
        """No preconditions. GitRepo construction validates git repo."""

    def plan(
        self,
        *,
        workspace: Workspace,
        uvr_state: UvrState,
        skill_state: SkillState,
    ) -> Plan:
        """(state, intent) -> plan."""
        root = workspace.root
        version = uvr_state.uvr_version
        commands: list[Command] = []

        if self.base_only:
            for skill_name, file_list in skill_state.skills.items():
                for skill_file in file_list:
                    rel_dest = f".claude/skills/{skill_name}/{skill_file.rel_path}"
                    commands.append(
                        WriteFileCommand(
                            label=f"Write merge base for {rel_dest}",
                            path=str(root / ".uvr" / "bases" / rel_dest),
                            content=skill_file.content,
                        )
                    )
            return Plan(jobs=[Job(name="upgrade_skill", commands=commands)])

        editor = uvr_state.editor or ""

        for skill_name, file_list in skill_state.skills.items():
            for skill_file in file_list:
                dest = root / ".claude" / "skills" / skill_name / skill_file.rel_path
                rel_dest = f".claude/skills/{skill_name}/{skill_file.rel_path}"
                fresh = skill_file.content

                if self.upgrade and rel_dest in skill_state.existing:
                    if rel_dest in skill_state.uncommitted:
                        continue  # skip files with uncommitted changes

                    base_text = skill_state.merge_bases.get(rel_dest, "")
                    commands.append(
                        MergeUpgradeCommand(
                            label=f"Merge upgrade {skill_name}/{skill_file.rel_path}",
                            dest_path=str(dest),
                            base_text=base_text,
                            fresh_text=fresh,
                            editor=editor,
                        )
                    )
                elif rel_dest in skill_state.existing and not self.force:
                    continue  # skip existing files without --force
                else:
                    # Fresh write (init or new file during upgrade)
                    commands.append(
                        WriteFileCommand(
                            label=f"Write {skill_name}/{skill_file.rel_path}",
                            path=str(dest),
                            content=fresh,
                        )
                    )

                # Write merge base
                commands.append(
                    WriteFileCommand(
                        label=f"Write merge base for {rel_dest}",
                        path=str(root / ".uvr" / "bases" / rel_dest),
                        content=fresh,
                    )
                )

        # Update skill_version
        commands.append(
            UpdateTomlCommand(
                label=f"Set skill_version to {version}",
                key="skill_version",
                value=version,
            )
        )

        return Plan(jobs=[Job(name="upgrade_skill", commands=commands)])
