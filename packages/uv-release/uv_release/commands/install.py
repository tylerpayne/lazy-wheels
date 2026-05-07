"""Install wheels command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from ..ui.console import console
from .base import Command


class InstallWheelsCommand(Command):
    """Install all wheels from a directory via uv pip install."""

    type: Literal["install_wheels"] = "install_wheels"
    dist_dir: str

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        wheels = list(Path(self.dist_dir).glob("*.whl"))
        if not wheels:
            console.print(f"    No wheels found in {self.dist_dir}")
            return 1
        args = ["uv", "pip", "install", "--find-links", self.dist_dir] + [
            str(w) for w in wheels
        ]
        result = subprocess.run(args)
        return result.returncode
