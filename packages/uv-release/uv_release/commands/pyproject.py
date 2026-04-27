"""Commands that mutate pyproject.toml files."""

from __future__ import annotations

from typing import Any, Literal

from ..types import Command, Package, PackagePyProjectDoc, Version


class SetVersionCommand(Command):
    """Set [project].version in a package's pyproject.toml."""

    type: Literal["set_version"] = "set_version"
    package: Package
    version: Version

    def execute(self) -> int:
        path = f"{self.package.path}/pyproject.toml"
        doc = PackagePyProjectDoc.read(path)
        doc.version = self.version.raw
        doc.write(path)
        return 0


class PinDepsCommand(Command):
    """Pin internal dependency versions in a package's pyproject.toml."""

    type: Literal["pin_deps"] = "pin_deps"
    package: Package
    pins: dict[str, Package]

    def execute(self) -> int:
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name

        path = f"{self.package.path}/pyproject.toml"
        doc = PackagePyProjectDoc.read(path)

        for dep_list in (doc.dependencies, doc.build_requires):
            for i, dep in enumerate(dep_list):
                req = Requirement(str(dep))
                name = canonicalize_name(req.name)
                if name in self.pins:
                    pinned = self.pins[name]
                    lower = pinned.version.raw
                    upper = pinned.version.bump_minor().raw
                    dep_list[i] = f"{req.name}>={lower},<{upper}"

        doc.write(path)
        return 0


class UpdateTomlCommand(Command):
    """Update a key in [tool.uvr.config] of the root pyproject.toml."""

    type: Literal["update_toml"] = "update_toml"
    key: str
    value: Any

    def execute(self) -> int:
        doc, path = _load_pyproject()
        if doc is None or path is None:
            return 1
        uvr = doc.setdefault("tool", {}).setdefault("uvr", {})
        uvr.setdefault("config", {})[self.key] = self.value
        path.write_text(_dumps_toml(doc))
        return 0


class WriteUvrSectionCommand(Command):
    """Write a complete section under [tool.uvr] in root pyproject.toml."""

    type: Literal["write_uvr_section"] = "write_uvr_section"
    section: str
    data: Any

    def execute(self) -> int:
        doc, path = _load_pyproject()
        if doc is None or path is None:
            return 1
        uvr = doc.setdefault("tool", {}).setdefault("uvr", {})
        uvr[self.section] = self.data
        path.write_text(_dumps_toml(doc))
        return 0


def _load_pyproject() -> tuple[Any, Any]:
    """Load pyproject.toml and return (doc, path), or (None, None) if missing."""
    import tomlkit
    from pathlib import Path

    path = Path("pyproject.toml")
    if not path.exists():
        return None, None
    doc = tomlkit.loads(path.read_text())
    return doc, path


def _dumps_toml(doc: Any) -> str:
    """Serialize a tomlkit document."""
    import tomlkit

    return tomlkit.dumps(doc)
