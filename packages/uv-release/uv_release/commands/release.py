"""GitHub release command."""

from __future__ import annotations

import glob
import subprocess
from typing import Literal

from pydantic import Field

from ..ui.console import console
from .base import Command


class CreateReleaseCommand(Command):
    """Create a GitHub release with wheel files attached."""

    type: Literal["create_release"] = "create_release"
    tag_name: str
    title: str
    notes: str
    files: list[str] = Field(default_factory=list)
    make_latest: bool = False

    def execute(self) -> int:
        # Check if release already exists.
        check = subprocess.run(
            ["gh", "release", "view", self.tag_name],
            capture_output=True,
        )
        if check.returncode == 0:
            # Release exists. Upload any missing assets.
            return self._upload_missing_assets()

        if self.label:
            console.print(f"  {self.label}")
        args = [
            "gh",
            "release",
            "create",
            self.tag_name,
            "--title",
            self.title,
            "--notes",
            self.notes,
        ]
        if self.make_latest:
            args.append("--latest")
        else:
            args.append("--latest=false")
        # Expand globs at execution time since wheels don't exist at plan time.
        for pattern in self.files:
            expanded = glob.glob(pattern)
            args.extend(expanded if expanded else [pattern])
        result = subprocess.run(args)
        return result.returncode

    def _upload_missing_assets(self) -> int:
        """Upload any files not already attached to an existing release."""
        import json

        # List existing assets on the release.
        result = subprocess.run(
            ["gh", "release", "view", self.tag_name, "--json", "assets"],
            capture_output=True,
            text=True,
        )
        existing_names: set[str] = set()
        if result.returncode == 0:
            try:
                assets = json.loads(result.stdout).get("assets", [])
                existing_names = {a["name"] for a in assets}
            except (json.JSONDecodeError, KeyError):
                pass

        # Expand globs and find files not yet uploaded.
        from pathlib import Path

        missing: list[str] = []
        for pattern in self.files:
            for path in glob.glob(pattern):
                if Path(path).name not in existing_names:
                    missing.append(path)

        if not missing:
            if self.label:
                console.print(f"  {self.label} (already exists, skipping)")
            return 0

        if self.label:
            console.print(f"  {self.label} (uploading {len(missing)} missing assets)")
        args = ["gh", "release", "upload", self.tag_name, "--clobber", *missing]
        result = subprocess.run(args)
        return result.returncode
