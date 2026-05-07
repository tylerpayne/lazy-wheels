"""Package index publishing command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from ..ui.console import console
from .base import Command


class PublishToIndexCommand(Command):
    """Publish wheels to a package index."""

    type: Literal["publish_to_index"] = "publish_to_index"
    package_name: str
    dist_dir: str = "dist"
    index: str = ""

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        # Glob for wheels matching this package in the dist directory.
        dist_name = self.package_name.replace("-", "_")
        wheels = list(Path(self.dist_dir).glob(f"{dist_name}-*.whl"))
        if not wheels:
            console.print(
                f"    No wheels found for {self.package_name} in {self.dist_dir}"
            )
            return 1
        args = ["uv", "publish"]
        if self.index:
            args.extend(["--index", self.index])
        args.extend(str(w) for w in wheels)
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = result.stderr or ""
            # PyPI rejects duplicate uploads. Treat as success on re-run.
            if "already exists" in stderr or "File already exists" in stderr:
                console.print("    Already published, skipping")
                return 0
            # Print stderr for real failures.
            if stderr:
                console.print(stderr, end="")
        if result.stdout:
            console.print(result.stdout, end="")
        return result.returncode
