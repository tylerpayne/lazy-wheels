"""The ``uvr workflow runners`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from ...shared.utils.cli import discover_package_names, fatal, print_matrix_status
from ...shared.utils.config import get_matrix, set_matrix
from ...shared.utils.toml import read_pyproject, write_pyproject
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
        fatal("No pyproject.toml found in current directory.")

    doc = read_pyproject(pyproject)
    matrix = get_matrix(doc)

    pkg = parsed.package
    add_runners = parsed.add_runners
    remove_runners = parsed.remove_runners
    clear = parsed.clear

    # No package -> show all (fill in defaults for unconfigured packages)
    if not pkg:
        all_packages = discover_package_names()
        effective = {name: matrix.get(name, _DEFAULT_RUNNERS) for name in all_packages}
        print_matrix_status(effective)
        return

    # --clear
    if clear:
        if pkg in matrix:
            del matrix[pkg]
            set_matrix(doc, matrix)
            write_pyproject(pyproject, doc)
            print(f"Cleared runners for '{pkg}'.")
        else:
            print(f"'{pkg}' has no runners configured.")
        return

    # --add RUNNER [RUNNER ...] (each argument is a separate runner)
    if add_runners is not None:
        runners = matrix.get(pkg, [])
        added: list[str] = []
        for runner in add_runners:
            labels = [s.strip() for s in runner.split(",")]
            if labels in runners:
                print(f"'{runner}' already in runners for '{pkg}'.")
                continue
            runners.append(labels)
            added.append(f"[{', '.join(labels)}]")
        if added:
            matrix[pkg] = runners
            set_matrix(doc, matrix)
            write_pyproject(pyproject, doc)
            print(f"Added {', '.join(added)} to '{pkg}' runners.")
        return

    # --remove RUNNER [RUNNER ...] (each argument is a separate runner)
    if remove_runners is not None:
        runners = matrix.get(pkg, [])
        removed: list[str] = []
        for runner in remove_runners:
            labels = [s.strip() for s in runner.split(",")]
            if labels not in runners:
                fatal(f"[{', '.join(labels)}] not in runners for '{pkg}'")
            runners.remove(labels)
            removed.append(f"[{', '.join(labels)}]")
        if runners:
            matrix[pkg] = runners
        else:
            del matrix[pkg]
        set_matrix(doc, matrix)
        write_pyproject(pyproject, doc)
        print(f"Removed {', '.join(removed)} from '{pkg}' runners.")
        return

    # Read
    runners = matrix.get(pkg, _DEFAULT_RUNNERS)
    for r in runners:
        print(f"  [{', '.join(r)}]")
