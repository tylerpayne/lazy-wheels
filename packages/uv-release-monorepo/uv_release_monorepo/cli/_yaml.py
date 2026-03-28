"""YAML navigation helpers for reading and writing nested dicts."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

_MISSING = object()


def _coerce_key(key: str, node: object) -> str | int:
    """If *node* is a list and *key* looks like an integer index, return int."""
    if isinstance(node, list):
        try:
            return int(key)
        except ValueError:
            pass
    return key


def _yaml_get(doc: dict | list, keys: list[str]) -> Any:
    """Navigate a nested dict/list by key path. Returns _MISSING if not found."""
    node: Any = doc
    for key in keys:
        k = _coerce_key(key, node)
        if isinstance(node, dict):
            if k not in node:
                return _MISSING
            node = node[k]
        elif isinstance(node, list) and isinstance(k, int):
            if k < 0 or k >= len(node):
                return _MISSING
            node = node[k]
        else:
            return _MISSING
    return node


def _yaml_set(doc: dict | list, keys: list[str], value: object) -> None:
    """Set a value at a key path, creating intermediate dicts as needed."""
    node: Any = doc
    for i, key in enumerate(keys[:-1]):
        k = _coerce_key(key, node)
        if isinstance(node, dict):
            if k not in node:
                node[k] = {}
                node = node[k]
            else:
                child = node[k]
                # If the next key targets a list index, let it through
                if isinstance(child, (dict, list)):
                    node = child
                else:
                    # Overwrite scalar with dict for remaining traversal
                    node[k] = {}
                    node = node[k]
        elif isinstance(node, list) and isinstance(k, int):
            node = node[k]
        else:
            raise KeyError(
                f"Cannot traverse into {type(node).__name__} with key {key!r}"
            )
    last = _coerce_key(keys[-1], node)
    if isinstance(node, list) and isinstance(last, int):
        node[last] = value
    elif isinstance(node, dict):
        node[last] = value


def _yaml_delete(doc: dict | list, keys: list[str]) -> bool:
    """Delete a key at a path. Returns True if deleted, False if not found."""
    node: Any = doc
    for key in keys[:-1]:
        k = _coerce_key(key, node)
        if isinstance(node, dict):
            if k not in node:
                return False
            node = node[k]
        elif isinstance(node, list) and isinstance(k, int):
            if k < 0 or k >= len(node):
                return False
            node = node[k]
        else:
            return False
    last = _coerce_key(keys[-1], node)
    if isinstance(node, dict) and last in node:
        del node[last]
        return True
    if isinstance(node, list) and isinstance(last, int):
        if 0 <= last < len(node):
            del node[last]
            return True
    return False


def _load_yaml(path: Path) -> dict:
    """Load a YAML file using ruamel.yaml (preserves order, quotes, comments)."""
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 2**31
    with open(path) as f:
        doc = yaml.load(f)
    return doc or {}


def _literalize_multiline(node: Any) -> Any:
    """Recursively wrap multiline strings as LiteralScalarString for block style."""
    from ruamel.yaml.scalarstring import LiteralScalarString

    if isinstance(node, dict):
        return {k: _literalize_multiline(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_literalize_multiline(v) for v in node]
    if isinstance(node, str) and "\n" in node:
        # Ensure trailing newline for clean block scalar rendering
        return LiteralScalarString(node if node.endswith("\n") else node + "\n")
    return node


def _dump_yaml(doc: Any) -> str:
    """Serialize a dict to YAML string using ruamel.yaml."""
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 2**31  # effectively infinite -- never line-wrap
    stream = StringIO()
    yaml.dump(_literalize_multiline(doc), stream)
    return stream.getvalue()


def _write_yaml(path: Path, doc: dict) -> None:
    """Write a dict to a YAML file using ruamel.yaml."""
    path.write_text(_dump_yaml(doc))
