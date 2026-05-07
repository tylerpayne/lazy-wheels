"""Version and dependency pinning commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from ..ui.console import console
from .base import Command
from ..utils.deps import parse_dep_name


class SetVersionCommand(Command):
    """Set a package's version in its pyproject.toml."""

    type: Literal["set_version"] = "set_version"
    package_path: str
    version: str

    def execute(self) -> int:
        import tomlkit

        if self.label:
            console.print(f"  {self.label}")
        path = Path(self.package_path) / "pyproject.toml"
        doc = tomlkit.loads(path.read_text())
        doc["project"]["version"] = self.version  # type: ignore[index]
        path.write_text(tomlkit.dumps(doc))
        return 0

    def to_shell(self) -> str:
        return f"uv version {self.version} --directory {self.package_path}"


class PinDepsCommand(Command):
    """Pin internal dependency versions in a package's pyproject.toml."""

    type: Literal["pin_deps"] = "pin_deps"
    package_path: str
    pins: dict[str, str]

    def execute(self) -> int:
        import tomlkit

        if self.label:
            console.print(f"  {self.label}")
        path = Path(self.package_path) / "pyproject.toml"
        doc = tomlkit.loads(path.read_text())
        deps = doc["project"].get("dependencies", [])  # type: ignore[union-attr]
        new_deps: list[Any] = []
        for dep in deps:
            name = parse_dep_name(str(dep))
            if name in self.pins:
                new_deps.append(self.pins[name])
            else:
                new_deps.append(dep)
        doc["project"]["dependencies"] = new_deps  # type: ignore[index]
        path.write_text(tomlkit.dumps(doc))
        return 0

    def to_shell(self) -> str:
        # No single shell command pins specific deps in a pyproject.toml
        # without rewriting the table. Show a comment with the resulting pins
        # so the user can spot what would change without us pretending it's
        # a one-liner.
        pins = ", ".join(self.pins.values())
        return f"# pin in {self.package_path}/pyproject.toml: {pins}"
