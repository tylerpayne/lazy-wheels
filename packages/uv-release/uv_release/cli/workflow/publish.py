"""The ``uvr workflow publish`` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tomlkit

from .._args import CommandArgs
from .runners import _discover_package_names


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
        print("ERROR: No pyproject.toml found.", file=sys.stderr)
        sys.exit(1)

    doc = tomlkit.loads(pyproject.read_text())
    config = dict(doc.get("tool", {}).get("uvr", {}).get("publish", {}))

    if parsed.clear:
        config = {
            "index": "",
            "environment": "",
            "trusted-publishing": "automatic",
            "include": [],
            "exclude": [],
        }
        _write_publish(pyproject, doc, config)
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
        all_packages = _discover_package_names(root, doc)
        _print_publish(config, all_packages)
        return

    if parsed.index is not None:
        config["index"] = parsed.index
    if parsed.environment is not None:
        config["environment"] = parsed.environment
    if parsed.trusted_publishing is not None:
        config["trusted-publishing"] = parsed.trusted_publishing

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

    _write_publish(pyproject, doc, config)
    print("Updated publish config.")


def _write_publish(pyproject: Path, doc: tomlkit.TOMLDocument, config: dict) -> None:
    tool = doc.setdefault("tool", {})
    uvr = tool.setdefault("uvr", {})
    uvr["publish"] = config
    pyproject.write_text(tomlkit.dumps(doc))


def _print_publish(config: dict, all_packages: list[str]) -> None:
    index = config.get("index", "")
    environment = config.get("environment", "")
    trusted = config.get("trusted-publishing", "automatic")
    include = config.get("include", [])
    exclude = config.get("exclude", [])

    if not any([index, environment, include, exclude]):
        print("No publish config set. All packages publish to the default index.")
        return

    if index:
        print(f"  index:              {index}")
    if environment:
        print(f"  environment:        {environment}")
    print(f"  trusted-publishing: {trusted}")
    if include:
        print(f"  include:            {', '.join(include)}")
    if exclude:
        print(f"  exclude:            {', '.join(exclude)}")
