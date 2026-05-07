"""Fetch template content from a specific uv-release version via uvx.

Used by `uvr workflow install --upgrade` and `uvr skill install --upgrade` to
populate `.uvr/bases/` with the template content from the user's last-accepted
uv-release version. The bases folder is treated as a transient cache. The
authoritative record of "what version did the user last accept" lives in
[tool.uvr.config].workflow-version / skill-version in pyproject.toml.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Literal

from ..ui.console import console
from .base import Command


class FetchWorkflowBaseCommand(Command):
    """Fetch the workflow template from a specific uv-release version.

    Spawns `uvx --from uv-release=={from_version} uvr workflow install
    --print-template` and writes stdout to output_path.
    """

    type: Literal["fetch_workflow_base"] = "fetch_workflow_base"
    from_version: str
    output_path: str

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        result = subprocess.run(
            [
                "uvx",
                "--from",
                f"uv-release=={self.from_version}",
                "uvr",
                "workflow",
                "install",
                "--print-template",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode != 0:
            console.print(
                f"    Failed to fetch workflow base for uv-release"
                f" {self.from_version}: {result.stderr.strip()}"
            )
            return result.returncode
        out = Path(self.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.stdout, encoding="utf-8")
        return 0


class FetchSkillBasesCommand(Command):
    """Fetch every bundled skill template from a specific uv-release version.

    Spawns `uvx --from uv-release=={from_version} uvr skill install
    --print-template`, parses the JSON map of {skill_name: [{rel_path,
    content}, ...]}, and writes each file under output_root/<skill>/<rel_path>.
    """

    type: Literal["fetch_skill_bases"] = "fetch_skill_bases"
    from_version: str
    output_root: str

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        result = subprocess.run(
            [
                "uvx",
                "--from",
                f"uv-release=={self.from_version}",
                "uvr",
                "skill",
                "install",
                "--print-template",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode != 0:
            console.print(
                f"    Failed to fetch skill bases for uv-release"
                f" {self.from_version}: {result.stderr.strip()}"
            )
            return result.returncode
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            console.print(f"    Could not parse skill template payload: {exc}")
            return 1
        root = Path(self.output_root)
        for skill_name, files in payload.items():
            for entry in files:
                rel = entry.get("rel_path", "")
                content = entry.get("content", "")
                if not rel:
                    continue
                target = root / skill_name / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        return 0
