"""The ``uvr workflow config`` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tomlkit

from .._args import CommandArgs


class ConfigArgs(CommandArgs):
    """Typed arguments for ``uvr workflow config``."""

    editor: str | None = None
    latest: str | None = None
    include_packages: list[str] | None = None
    exclude_packages: list[str] | None = None
    remove_packages: list[str] | None = None
    clear: bool = False


def cmd_config(args: argparse.Namespace) -> None:
    """Manage workspace config in [tool.uvr.config]."""
    parsed = ConfigArgs.from_namespace(args)
    root = Path.cwd()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        print("ERROR: No pyproject.toml found.", file=sys.stderr)
        sys.exit(1)

    doc = tomlkit.loads(pyproject.read_text())
    config = dict(doc.get("tool", {}).get("uvr", {}).get("config", {}))

    if parsed.clear:
        config = {"include": [], "exclude": [], "latest": "", "editor": ""}
        _write_config(pyproject, doc, config)
        print("Cleared workspace config.")
        return

    has_mutations = any(
        [
            parsed.editor is not None,
            parsed.latest is not None,
            parsed.include_packages is not None,
            parsed.exclude_packages is not None,
            parsed.remove_packages is not None,
        ]
    )

    if not has_mutations:
        _print_config(config)
        return

    if parsed.editor is not None:
        config["editor"] = parsed.editor
    if parsed.latest is not None:
        config["latest"] = parsed.latest

    include: list[str] = list(config.get("include", []))
    exclude: list[str] = list(config.get("exclude", []))

    if parsed.include_packages is not None:
        for pkg in parsed.include_packages:
            if pkg not in include:
                include.append(pkg)
        if parsed.remove_packages is not None:
            for pkg in parsed.remove_packages:
                if pkg in include:
                    include.remove(pkg)

    elif parsed.exclude_packages is not None:
        for pkg in parsed.exclude_packages:
            if pkg not in exclude:
                exclude.append(pkg)
        if parsed.remove_packages is not None:
            for pkg in parsed.remove_packages:
                if pkg in exclude:
                    exclude.remove(pkg)

    elif parsed.remove_packages is not None:
        for pkg in parsed.remove_packages:
            if pkg in include:
                include.remove(pkg)
            if pkg in exclude:
                exclude.remove(pkg)

    config["include"] = include
    config["exclude"] = exclude

    _write_config(pyproject, doc, config)
    print("Updated workspace config.")


def _write_config(pyproject: Path, doc: tomlkit.TOMLDocument, config: dict) -> None:
    """Write config back to [tool.uvr.config]."""
    tool = doc.setdefault("tool", {})
    uvr = tool.setdefault("uvr", {})
    uvr["config"] = config
    pyproject.write_text(tomlkit.dumps(doc))


def _print_config(config: dict) -> None:
    """Print the current workspace config."""
    include = config.get("include", [])
    exclude = config.get("exclude", [])
    latest = config.get("latest", "")
    editor = config.get("editor", "")

    if not any([include, exclude, latest, editor]):
        print("No workspace config set.")
        return

    if include:
        print(f"  include: {', '.join(include)}")
    if exclude:
        print(f"  exclude: {', '.join(exclude)}")
    if latest:
        print(f"  latest:  {latest}")
    if editor:
        print(f"  editor:  {editor}")
