"""TOML manipulation commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from ..ui.console import console
from .base import Command


class UpdateTomlCommand(Command):
    """Update a key in [tool.uvr.config] of root pyproject.toml."""

    type: Literal["update_toml"] = "update_toml"
    key: str
    value: str | list[str] | bool

    def execute(self) -> int:
        import tomlkit

        if self.label:
            console.print(f"  {self.label}")
        path = Path("pyproject.toml")
        doc = tomlkit.loads(path.read_text())
        tool = doc.setdefault("tool", {})
        uvr = tool.setdefault("uvr", {})
        config = uvr.setdefault("config", {})
        config[self.key] = self.value
        path.write_text(tomlkit.dumps(doc))
        return 0


class WriteUvrSectionCommand(Command):
    """Write an entire section under [tool.uvr] in root pyproject.toml."""

    type: Literal["write_uvr_section"] = "write_uvr_section"
    section: str
    data: dict[str, Any]

    def execute(self) -> int:
        import tomlkit

        if self.label:
            console.print(f"  {self.label}")
        path = Path("pyproject.toml")
        doc = tomlkit.loads(path.read_text())
        tool = doc.setdefault("tool", {})
        uvr = tool.setdefault("uvr", {})
        uvr[self.section] = self.data
        path.write_text(tomlkit.dumps(doc))
        return 0
