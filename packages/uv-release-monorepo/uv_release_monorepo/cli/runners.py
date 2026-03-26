"""The ``uvr runners`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..shared.toml import get_uvr_matrix, load_pyproject, save_pyproject, set_uvr_matrix
from ._common import _fatal, _print_matrix_status


def cmd_runners(args: argparse.Namespace) -> None:
    """Manage per-package build runners in [tool.uvr.matrix]."""
    root = Path.cwd()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        _fatal("No pyproject.toml found in current directory.")

    doc = load_pyproject(pyproject)
    matrix = get_uvr_matrix(doc)

    pkg: str | None = getattr(args, "package", None)
    add_val: str | None = getattr(args, "add_value", None)
    remove_val: str | None = getattr(args, "remove_value", None)
    clear: bool = getattr(args, "clear", False)

    # No package -> show all
    if not pkg:
        if not matrix:
            print("No runners configured. All packages build on ubuntu-latest.")
        else:
            _print_matrix_status(matrix)
        return

    # --clear
    if clear:
        if pkg in matrix:
            del matrix[pkg]
            set_uvr_matrix(doc, matrix)
            save_pyproject(pyproject, doc)
            print(f"Cleared runners for '{pkg}'.")
        else:
            print(f"'{pkg}' has no runners configured.")
        return

    # --add
    if add_val is not None:
        runners = matrix.get(pkg, [])
        if add_val in runners:
            print(f"'{add_val}' already in runners for '{pkg}'.")
            return
        runners.append(add_val)
        matrix[pkg] = runners
        set_uvr_matrix(doc, matrix)
        save_pyproject(pyproject, doc)
        print(f"Added '{add_val}' to '{pkg}' runners.")
        return

    # --remove
    if remove_val is not None:
        runners = matrix.get(pkg, [])
        if remove_val not in runners:
            _fatal(f"'{remove_val}' not in runners for '{pkg}'")
        runners.remove(remove_val)
        if runners:
            matrix[pkg] = runners
        else:
            del matrix[pkg]
        set_uvr_matrix(doc, matrix)
        save_pyproject(pyproject, doc)
        print(f"Removed '{remove_val}' from '{pkg}' runners.")
        return

    # Read
    runners = matrix.get(pkg)
    if runners:
        print(", ".join(runners))
    else:
        print(f"'{pkg}' has no runners configured (defaults to ubuntu-latest).")
