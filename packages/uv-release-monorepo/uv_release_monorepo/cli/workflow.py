"""The ``uvr workflow`` command."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..models import ReleaseWorkflow
from ._common import _fatal
from ._yaml import _MISSING, _yaml_delete, _yaml_get, _yaml_set


def cmd_workflow(args: argparse.Namespace) -> None:
    """Read, write, or delete any key in the release workflow YAML."""
    import yaml

    root = Path.cwd()
    workflow_dir = getattr(args, "workflow_dir", ".github/workflows")
    release_yml = root / workflow_dir / "release.yml"
    if not release_yml.exists():
        _fatal("No release.yml found. Run `uvr init` first to generate the workflow.")

    with open(release_yml) as f:
        doc = yaml.safe_load(f) or {}

    parts: list[str] = getattr(args, "path", []) or []
    set_value: str | None = getattr(args, "set_value", None)
    add_value: str | None = getattr(args, "add_value", None)
    insert_value: str | None = getattr(args, "insert_value", None)
    remove_value: str | None = getattr(args, "remove_value", None)
    insert_index: int | None = getattr(args, "insert_index", None)
    clear: bool = getattr(args, "clear", False)

    def _dump(val: object) -> str:
        if isinstance(val, (dict, list)):
            return yaml.dump(val, default_flow_style=False, sort_keys=False).rstrip()
        return str(val)

    def _validate_and_write() -> None:
        from pydantic import ValidationError

        try:
            model = ReleaseWorkflow.model_validate(doc)
        except ValidationError as e:
            _fatal(f"Invalid workflow structure:\n{e}")
        release_yml.write_text(
            yaml.dump(
                model.model_dump(by_alias=True, exclude_none=True),
                default_flow_style=False,
                sort_keys=False,
            )
        )

    path_str = ".".join(parts)

    # No path -> dump entire doc
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
        value = yaml.safe_load(set_value)
        _yaml_set(doc, parts, value)
        _validate_and_write()
        print(f"Set '{path_str}': {set_value}")
        return

    # --add
    if add_value is not None:
        value = yaml.safe_load(add_value)
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
        value = yaml.safe_load(insert_value)
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
        value = yaml.safe_load(remove_value)
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
