"""SkillUpgradeJob: scaffold or upgrade Claude Code skill files.

Three install modes (mirroring workflow install):
- no flags: scaffold any missing skill files. Files that already exist are
  left untouched (no error, since skills are scaffolded together and an
  individual file may have been added in a later release).
- --upgrade: three-way merge each existing file using the base from the
  previously-recorded skill-version, fetched via uvx.
- --force: overwrite every skill file with the current template.

skill-version in [tool.uvr.config] is updated only after a successful upgrade
or force run. The .uvr/bases/ folder is a transient cache populated by the
fetch command at the start of an --upgrade.
"""

from __future__ import annotations

from pathlib import Path

from diny import singleton, provider

from ...commands import (
    AnyCommand,
    FetchSkillBasesCommand,
    MergeUpgradeCommand,
    UpdateTomlCommand,
    WriteFileCommand,
)
from ...types.job import Job
from ..config.uvr_config import UvrConfig
from ..params.skill_params import SkillParams
from ..shared.git_repo import GitRepo
from ..shared.skill_template import SkillTemplate


@singleton
class SkillUpgradeJob(Job):
    """Upgrade skill template files."""


_SKILL_BASE_ROOT = Path(".uvr") / "bases" / ".claude" / "skills"


@provider(SkillUpgradeJob)
def provide_skill_upgrade_job(
    params: SkillParams,
    template: SkillTemplate,
    git_repo: GitRepo,
    config: UvrConfig,
) -> SkillUpgradeJob:
    if not template.skills:
        msg = "No skill templates found. Is uv-release installed correctly?"
        raise ValueError(msg)

    commands: list[AnyCommand] = []

    # Scaffold any missing skill files first. Missing files always get written,
    # regardless of mode, so the user picks up newly-added skill files.
    any_existing = False
    for skill_name, files in template.skills.items():
        skill_dir = Path(".claude") / "skills" / skill_name
        for skill_file in files:
            target = skill_dir / skill_file.rel_path
            if not target.exists():
                commands.append(
                    WriteFileCommand(
                        label=f"Create {target}",
                        path=str(target),
                        content=skill_file.content,
                    )
                )
            else:
                any_existing = True

    # If nothing existed before, scaffold-only is enough. Record the version.
    if not any_existing:
        commands.append(
            UpdateTomlCommand(
                label=f"Record skill-version={template.version}",
                key="skill-version",
                value=template.version,
            )
        )
        return SkillUpgradeJob(name="skill-upgrade", commands=commands)

    # Some files exist. Bare `install` is an error: user must pick a mode.
    if not params.upgrade and not params.force:
        msg = (
            "Skill files already exist. "
            "Use --upgrade to three-way-merge with the bundled templates, "
            "or --force to overwrite."
        )
        raise ValueError(msg)

    if params.upgrade:
        if not config.skill_version:
            msg = (
                "No skill-version recorded in [tool.uvr.config]. "
                "Cannot --upgrade without knowing the previous template version. "
                "Use --force to reset to the current templates."
            )
            raise ValueError(msg)
        # One fetch populates every base file under .uvr/bases/.claude/skills/.
        commands.append(
            FetchSkillBasesCommand(
                label=f"Fetch skill bases from uv-release {config.skill_version}",
                from_version=config.skill_version,
                output_root=str(_SKILL_BASE_ROOT),
            )
        )
        for skill_name, files in template.skills.items():
            skill_dir = Path(".claude") / "skills" / skill_name
            base_dir = _SKILL_BASE_ROOT / skill_name
            for skill_file in files:
                target = skill_dir / skill_file.rel_path
                if not target.exists():
                    continue
                # Skip dirty files unless --force (which we already excluded).
                if git_repo.file_is_dirty(str(target)):
                    continue
                base_path = base_dir / skill_file.rel_path
                commands.append(
                    MergeUpgradeCommand(
                        label=f"Upgrade {target}",
                        file_path=str(target),
                        base_path=str(base_path),
                        incoming_content=skill_file.content,
                        editor=params.editor,
                    )
                )
    else:
        # --force: overwrite each file with the current template.
        for skill_name, files in template.skills.items():
            skill_dir = Path(".claude") / "skills" / skill_name
            for skill_file in files:
                target = skill_dir / skill_file.rel_path
                if not target.exists():
                    continue
                commands.append(
                    WriteFileCommand(
                        label=f"Overwrite {target}",
                        path=str(target),
                        content=skill_file.content,
                    )
                )

    commands.append(
        UpdateTomlCommand(
            label=f"Record skill-version={template.version}",
            key="skill-version",
            value=template.version,
        )
    )
    return SkillUpgradeJob(name="skill-upgrade", commands=commands)
