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
    package_name: str
    package_path: str
    version: str

    def execute(self) -> int:
        import tomlkit

        path = Path(self.package_path) / "pyproject.toml"
        doc = tomlkit.loads(path.read_text())
        old = str(doc["project"]["version"])  # type: ignore[index]
        # Print our own diff line in the design grammar: package + versions
        # in cyan (refs the system tracks), arrow in dim (chrome). The
        # package name is passed in rather than derived from the path,
        # because path="." (single-package layout) has no basename.
        console.print(
            f"  Updated [uvr.value]{self.package_name}[/] "
            f"[uvr.value]v{old}[/] [uvr.dim]->[/] [uvr.value]v{self.version}[/]"
        )
        doc["project"]["version"] = self.version  # type: ignore[index]
        path.write_text(tomlkit.dumps(doc))
        return 0


class PinDepsCommand(Command):
    """Pin internal dependency versions in a package's pyproject.toml.

    Rewrites matching entries in both `[project].dependencies` and
    `[build-system].requires` so a workspace package that build-depends
    on a sibling stays consistent across the release.
    """

    type: Literal["pin_deps"] = "pin_deps"
    package_path: str
    pins: dict[str, str]

    def execute(self) -> int:
        import tomlkit

        if self.label:
            console.print(f"  {self.label}")
        path = Path(self.package_path) / "pyproject.toml"
        doc = tomlkit.loads(path.read_text())

        project = doc.get("project")
        if project is not None:
            deps = project.get("dependencies", [])
            project["dependencies"] = _rewrite_pins(deps, self.pins)

        build_system = doc.get("build-system")
        if build_system is not None:
            requires = build_system.get("requires", [])
            build_system["requires"] = _rewrite_pins(requires, self.pins)

        path.write_text(tomlkit.dumps(doc))
        return 0


def _rewrite_pins(items: list[Any], pins: dict[str, str]) -> list[Any]:
    rewritten: list[Any] = []
    for item in items:
        name = parse_dep_name(str(item))
        if name in pins:
            rewritten.append(pins[name])
        else:
            rewritten.append(item)
    return rewritten
