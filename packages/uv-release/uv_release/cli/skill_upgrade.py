"""uvr skill upgrade: scaffold or upgrade Claude Code skill files."""

from __future__ import annotations

import json
import sys

from diny import inject

from .. import ui
from ..dependencies.params.skill_params import SkillParams
from ..dependencies.shared.skill_template import SkillTemplate
from ..dependencies.skill.upgrade_job import SkillUpgradeJob
from ..execute import execute_job


@inject
def cmd_skill_upgrade(
    params: SkillParams,
    template: SkillTemplate,
    upgrade_job: SkillUpgradeJob,
) -> None:
    # --print-template short-circuits, dumping every bundled skill file as JSON.
    # Consumed by --upgrade via uvx; MUST stay byte-exact (no Rich) so the
    # downstream JSON parser works.
    if params.print_template:
        payload = {
            name: [{"rel_path": f.rel_path, "content": f.content} for f in files]
            for name, files in template.skills.items()
        }
        json.dump(payload, sys.stdout)
        return

    if not upgrade_job.commands:
        ui.console.print("Skills are already up to date.")
        return

    execute_job(upgrade_job)
