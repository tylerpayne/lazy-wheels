"""The ``uvr workflow runners`` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tomlkit

from .._args import CommandArgs

_DEFAULT_RUNNERS: list[list[str]] = [["ubuntu-latest"]]


class RunnersArgs(CommandArgs):
    """Typed arguments for ``uvr workflow runners``."""

    package: str | None = None
    add_runners: list[str] | None = None
    remove_runners: list[str] | None = None
    clear: bool = False


def cmd_runners(args: argparse.Namespace) -> None:
    """Manage per-package build runners in [tool.uvr.runners]."""
    parsed = RunnersArgs.from_namespace(args)
    root = Path.cwd()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        print("ERROR: No pyproject.toml found.", file=sys.stderr)
        sys.exit(1)

    doc = tomlkit.loads(pyproject.read_text())
    matrix: dict[str, list[list[str]]] = dict(
        doc.get("tool", {}).get("uvr", {}).get("runners", {})
    )

    pkg = parsed.package

    if not pkg:
        all_packages = _discover_package_names(root, doc)
        effective = {name: matrix.get(name, _DEFAULT_RUNNERS) for name in all_packages}
        _print_runners(effective)
        return

    if parsed.clear:
        if pkg in matrix:
            del matrix[pkg]
            _write_runners(pyproject, doc, matrix)
            print(f"Cleared runners for '{pkg}'.")
        else:
            print(f"'{pkg}' has no runners configured.")
        return

    if parsed.add_runners is not None:
        runners = matrix.get(pkg, [])
        added: list[str] = []
        for runner in parsed.add_runners:
            labels = [s.strip() for s in runner.split(",")]
            if labels in runners:
                print(f"'{runner}' already in runners for '{pkg}'.")
                continue
            runners.append(labels)
            added.append(f"[{', '.join(labels)}]")
        if added:
            matrix[pkg] = runners
            _write_runners(pyproject, doc, matrix)
            print(f"Added {', '.join(added)} to '{pkg}' runners.")
        return

    if parsed.remove_runners is not None:
        runners = matrix.get(pkg, [])
        removed: list[str] = []
        for runner in parsed.remove_runners:
            labels = [s.strip() for s in runner.split(",")]
            if labels not in runners:
                print(
                    f"ERROR: [{', '.join(labels)}] not in runners for '{pkg}'",
                    file=sys.stderr,
                )
                sys.exit(1)
            runners.remove(labels)
            removed.append(f"[{', '.join(labels)}]")
        if runners:
            matrix[pkg] = runners
        else:
            del matrix[pkg]
        _write_runners(pyproject, doc, matrix)
        print(f"Removed {', '.join(removed)} from '{pkg}' runners.")
        return

    runners = matrix.get(pkg, _DEFAULT_RUNNERS)
    for r in runners:
        print(f"  [{', '.join(r)}]")


def _write_runners(
    pyproject: Path, doc: tomlkit.TOMLDocument, matrix: dict[str, list[list[str]]]
) -> None:
    tool = doc.setdefault("tool", {})
    uvr = tool.setdefault("uvr", {})
    uvr["runners"] = matrix
    pyproject.write_text(tomlkit.dumps(doc))


def _discover_package_names(root: Path, doc: tomlkit.TOMLDocument) -> list[str]:
    """Discover workspace package names from pyproject.toml."""
    members_patterns = (
        doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    )
    names: list[str] = []
    for pattern in members_patterns:
        for pkg_dir in sorted(root.glob(pattern)):
            pkg_pyproject = pkg_dir / "pyproject.toml"
            if pkg_pyproject.exists():
                pkg_doc = tomlkit.loads(pkg_pyproject.read_text())
                name = pkg_doc.get("project", {}).get("name")
                if name:
                    names.append(name)
    return names


def _print_runners(effective: dict[str, list[list[str]]]) -> None:
    if not effective:
        print("No packages found.")
        return
    nw = max(len(n) for n in effective)
    for name, runners in sorted(effective.items()):
        labels = ", ".join(f"[{', '.join(r)}]" for r in runners)
        print(f"  {name.ljust(nw)}  {labels}")
