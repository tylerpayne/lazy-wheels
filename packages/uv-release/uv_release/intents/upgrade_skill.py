"""UpgradeSkillIntent: scaffold or upgrade Claude Code skill files."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..commands import MergeUpgradeCommand, UpdateTomlCommand, WriteFileCommand
from ..states.merge_bases import read_base, resolve_editor
from ..states.workspace import read_uvr_version
from ..states.worktree import has_uncommitted_changes
from ..types import Command, Job, Plan, Workspace

_SKILLS_TEMPLATE_DIR = files("uv_release").joinpath("templates/skills")


def _discover_skill_files() -> dict[str, list[str]]:
    """Discover skill files from the bundled template directory."""
    base = Path(str(_SKILLS_TEMPLATE_DIR))
    result: dict[str, list[str]] = {}
    for skill_dir in sorted(base.iterdir()):
        if not skill_dir.is_dir():
            continue
        file_list: list[str] = []
        for file_path in sorted(skill_dir.rglob("*")):
            if file_path.is_file():
                file_list.append(str(file_path.relative_to(skill_dir)))
        if file_list:
            result[skill_dir.name] = file_list
    return result


def _load_skill_file(skill_name: str, rel_path: str) -> str:
    base = Path(str(_SKILLS_TEMPLATE_DIR))
    path = base / skill_name / rel_path
    return path.read_text(encoding="utf-8")


class UpgradeSkillIntent(BaseModel):
    """Intent to scaffold or upgrade Claude Code skill files."""

    model_config = ConfigDict(frozen=True)

    type: Literal["upgrade_skill"] = "upgrade_skill"
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

    def plan(self, workspace: Workspace) -> Plan:
        """(state, intent) -> plan."""
        root = Path.cwd()
        version = read_uvr_version()
        commands: list[Command] = []

        if self.base_only:
            for skill_name, file_list in _discover_skill_files().items():
                for rel_path in file_list:
                    rel_dest = f".claude/skills/{skill_name}/{rel_path}"
                    content = _load_skill_file(skill_name, rel_path)
                    commands.append(
                        WriteFileCommand(
                            label=f"Write merge base for {rel_dest}",
                            path=str(root / ".uvr" / "bases" / rel_dest),
                            content=content,
                        )
                    )
            return Plan(jobs=[Job(name="upgrade_skill", commands=commands)])

        editor = resolve_editor(self.editor) or ""

        for skill_name, file_list in _discover_skill_files().items():
            for rel_path in file_list:
                dest = root / ".claude" / "skills" / skill_name / rel_path
                rel_dest = f".claude/skills/{skill_name}/{rel_path}"
                fresh = _load_skill_file(skill_name, rel_path)

                if self.upgrade and dest.exists():
                    if has_uncommitted_changes(dest):
                        continue  # skip files with uncommitted changes

                    base_text = read_base(root, rel_dest)
                    commands.append(
                        MergeUpgradeCommand(
                            label=f"Merge upgrade {skill_name}/{rel_path}",
                            dest_path=str(dest),
                            base_text=base_text,
                            fresh_text=fresh,
                            editor=editor,
                        )
                    )
                elif dest.exists() and not self.force:
                    continue  # skip existing files without --force
                else:
                    # Fresh write (init or new file during upgrade)
                    commands.append(
                        WriteFileCommand(
                            label=f"Write {skill_name}/{rel_path}",
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
