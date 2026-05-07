"""Dispatch release plan to GitHub Actions."""

from __future__ import annotations

import json
import subprocess
import time
from typing import Literal

from ..ui.console import console
from .base import Command


class DispatchWorkflowCommand(Command):
    """Serialize a plan and trigger the release workflow via gh CLI."""

    type: Literal["dispatch_workflow"] = "dispatch_workflow"
    plan_json: str

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not branch:
            console.print("    Could not determine current branch.")
            return 1
        result = subprocess.run(
            [
                "gh",
                "workflow",
                "run",
                "release.yml",
                "--ref",
                branch,
                "-f",
                f"plan={self.plan_json}",
            ]
        )
        if result.returncode != 0:
            return result.returncode
        self._poll()
        return 0

    def _poll(self) -> None:
        """Wait briefly then print the URL of the triggered run."""
        time.sleep(2)
        result = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--workflow=release.yml",
                "--limit=1",
                "--json",
                "databaseId,status,url",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return
        try:
            runs = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            return
        if runs:
            run = runs[0]
            console.print(f"    Run: {run.get('url', 'unknown')}")
            console.print(f"    Status: {run.get('status', 'unknown')}")
