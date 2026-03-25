"""The ``uvr workflow`` command."""

from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path
from typing import Any

from ..models import ReleaseWorkflow
from ._common import _fatal
from ._yaml import _MISSING, _yaml_delete, _yaml_get, _yaml_set


def _load_yaml(path: Path) -> dict:
    """Load a YAML file using ruamel.yaml (preserves order, quotes, comments)."""
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 2**31
    with open(path) as f:
        doc = yaml.load(f)
    return doc or {}


def _dump_yaml(doc: Any) -> str:
    """Serialize a dict to YAML string using ruamel.yaml."""
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 2**31  # effectively infinite -- never line-wrap
    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()


def _write_yaml(path: Path, doc: dict) -> None:
    """Write a dict to a YAML file using ruamel.yaml."""
    path.write_text(_dump_yaml(doc))


def cmd_workflow(args: argparse.Namespace) -> None:
    """Read, write, or delete any key in the release workflow YAML."""
    from ruamel.yaml import YAML

    root = Path.cwd()
    workflow_dir = getattr(args, "workflow_dir", ".github/workflows")
    release_yml = root / workflow_dir / "release.yml"
    if not release_yml.exists():
        _fatal("No release.yml found. Run `uvr init` first to generate the workflow.")

    doc = _load_yaml(release_yml)

    parts: list[str] = getattr(args, "path", []) or []
    set_value: str | None = getattr(args, "set_value", None)
    add_value: str | None = getattr(args, "add_value", None)
    insert_value: str | None = getattr(args, "insert_value", None)
    remove_value: str | None = getattr(args, "remove_value", None)
    insert_index: int | None = getattr(args, "insert_index", None)
    clear: bool = getattr(args, "clear", False)

    def _dump(val: Any) -> str:
        if isinstance(val, (dict, list)):
            return _dump_yaml(val).rstrip()
        return str(val)

    def _parse_value(raw: str) -> Any:
        """Parse a CLI value string as YAML (supports scalars, lists, dicts)."""
        yaml = YAML()
        return yaml.load(raw)

    def _validate_and_write() -> None:
        from pydantic import ValidationError

        # ruamel.yaml preserves `on:` as the string "on", no True mangling
        try:
            ReleaseWorkflow.model_validate(dict(doc))
        except ValidationError as e:
            _fatal(f"Invalid workflow structure:\n{e}")
        _write_yaml(release_yml, doc)

    path_str = ".".join(parts)

    # No path -- dump entire doc
    if not parts:
        print(_dump(doc))
        return

    # --clear
    if clear:
        if _yaml_delete(doc, parts):
            _validate_and_write()
            print(f"Deleted '{path_str}'.")
        else:
            print(f"'{path_str}': not found")
        return

    # --set
    if set_value is not None:
        value = _parse_value(set_value)
        _yaml_set(doc, parts, value)
        _validate_and_write()
        print(f"Set '{path_str}': {set_value}")
        return

    # --add
    if add_value is not None:
        value = _parse_value(add_value)
        current = _yaml_get(doc, parts)
        if current is _MISSING:
            _yaml_set(doc, parts, [value])
        elif isinstance(current, list):
            current.append(value)
        else:
            _fatal(f"'{path_str}' is not a list (got {type(current).__name__})")
        _validate_and_write()
        print(f"Added '{add_value}' to '{path_str}'.")
        return

    # --insert (requires --at)
    if insert_value is not None:
        if insert_index is None:
            _fatal("--insert requires --at INDEX")
        value = _parse_value(insert_value)
        current = _yaml_get(doc, parts)
        if current is _MISSING:
            _yaml_set(doc, parts, [value])
        elif isinstance(current, list):
            current.insert(insert_index, value)
        else:
            _fatal(f"'{path_str}' is not a list (got {type(current).__name__})")
        _validate_and_write()
        print(f"Inserted '{insert_value}' into '{path_str}' at {insert_index}.")
        return

    # --remove
    if remove_value is not None:
        value = _parse_value(remove_value)
        current = _yaml_get(doc, parts)
        if not isinstance(current, list):
            _fatal(f"'{path_str}' is not a list")
        try:
            current.remove(value)
        except ValueError:
            _fatal(f"'{remove_value}' not found in '{path_str}'")
        _validate_and_write()
        print(f"Removed '{remove_value}' from '{path_str}'.")
        return

    # Read
    val = _yaml_get(doc, parts)
    if val is not _MISSING:
        print(_dump(val))
    else:
        print(f"'{path_str}': not found")
