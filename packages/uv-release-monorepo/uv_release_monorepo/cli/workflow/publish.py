"""The ``uvr workflow publish`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from ...shared.utils.cli import discover_package_names, fatal, print_publish_status
from ...shared.utils.config import get_publish_config, set_publish_config
from ...shared.utils.toml import read_pyproject, write_pyproject
from .._args import CommandArgs


class PublishConfigArgs(CommandArgs):
    """Typed arguments for ``uvr workflow publish``."""

    index: str | None = None
    environment: str | None = None
    trusted_publishing: str | None = None
    include_packages: list[str] | None = None
    exclude_packages: list[str] | None = None
    remove_packages: list[str] | None = None
    clear: bool = False


def cmd_publish_config(args: argparse.Namespace) -> None:
    """Manage index publishing config in [tool.uvr.publish]."""
    parsed = PublishConfigArgs.from_namespace(args)
    root = Path.cwd()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        fatal("No pyproject.toml found in current directory.")

    doc = read_pyproject(pyproject)
    config = get_publish_config(doc)

    # --clear: remove entire section
    if parsed.clear:
        config = {
            "index": "",
            "environment": "",
            "trusted_publishing": "automatic",
            "include": [],
            "exclude": [],
        }
        set_publish_config(doc, config)
        write_pyproject(pyproject, doc)
        print("Cleared publish config.")
        return

    has_mutations = any(
        [
            parsed.index is not None,
            parsed.environment is not None,
            parsed.trusted_publishing is not None,
            parsed.include_packages is not None,
            parsed.exclude_packages is not None,
            parsed.remove_packages is not None,
        ]
    )

    if not has_mutations:
        # Show mode
        all_packages = discover_package_names()
        print_publish_status(config, all_packages)
        return

    # Apply scalar settings
    if parsed.index is not None:
        config["index"] = parsed.index
    if parsed.environment is not None:
        config["environment"] = parsed.environment
    if parsed.trusted_publishing is not None:
        config["trusted_publishing"] = parsed.trusted_publishing

    # Apply list operations
    include: list[str] = list(config.get("include", []))
    exclude: list[str] = list(config.get("exclude", []))

    if parsed.include_packages is not None:
        for pkg in parsed.include_packages:
            if pkg not in include:
                include.append(pkg)

        # --remove with --include: remove from include list
        if parsed.remove_packages is not None:
            for pkg in parsed.remove_packages:
                if pkg in include:
                    include.remove(pkg)

    elif parsed.exclude_packages is not None:
        for pkg in parsed.exclude_packages:
            if pkg not in exclude:
                exclude.append(pkg)

        # --remove with --exclude: remove from exclude list
        if parsed.remove_packages is not None:
            for pkg in parsed.remove_packages:
                if pkg in exclude:
                    exclude.remove(pkg)

    elif parsed.remove_packages is not None:
        # --remove alone: remove from both lists
        for pkg in parsed.remove_packages:
            if pkg in include:
                include.remove(pkg)
            if pkg in exclude:
                exclude.remove(pkg)

    config["include"] = include
    config["exclude"] = exclude

    set_publish_config(doc, config)
    write_pyproject(pyproject, doc)
    print("Updated publish config.")
