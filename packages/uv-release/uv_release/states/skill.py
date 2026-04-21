"""Skill files state for upgrade intent."""

from __future__ import annotations

import subprocess
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .base import State

_SKILLS_TEMPLATE_DIR = files("uv_release").joinpath("templates/skills")


class SkillFile(BaseModel):
    """A single skill file with its relative path and content."""

    model_config = ConfigDict(frozen=True)

    rel_path: str
    content: str


class SkillState(State):
    """Skill files state for upgrade intent."""

    skills: dict[str, list[SkillFile]] = Field(default_factory=dict)
    merge_bases: dict[str, str] = Field(default_factory=dict)
    uncommitted: frozenset[str] = frozenset()
    existing: frozenset[str] = frozenset()

    @classmethod
    def parse(cls) -> SkillState:
        """Discover skill files, read merge bases, and check uncommitted status."""
        root = Path.cwd()
        skills: dict[str, list[SkillFile]] = {}
        merge_bases: dict[str, str] = {}
        uncommitted_set: set[str] = set()
        existing_set: set[str] = set()

        base = Path(str(_SKILLS_TEMPLATE_DIR))
        for skill_dir in sorted(base.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_name = skill_dir.name
            file_list: list[SkillFile] = []
            for file_path in sorted(skill_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                rel_path = str(file_path.relative_to(skill_dir))
                content = file_path.read_text(encoding="utf-8")
                file_list.append(SkillFile(rel_path=rel_path, content=content))

                rel_dest = f".claude/skills/{skill_name}/{rel_path}"
                merge_bases[rel_dest] = _read_base(root, rel_dest)

                dest = root / ".claude" / "skills" / skill_name / rel_path
                if dest.exists():
                    existing_set.add(rel_dest)
                    if _has_uncommitted_changes(dest):
                        uncommitted_set.add(rel_dest)

            if file_list:
                skills[skill_name] = file_list

        return SkillState(
            skills=skills,
            merge_bases=merge_bases,
            uncommitted=frozenset(uncommitted_set),
            existing=frozenset(existing_set),
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
