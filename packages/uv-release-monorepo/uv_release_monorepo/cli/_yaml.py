"""YAML navigation helpers for reading and writing nested dicts."""

from __future__ import annotations

_MISSING = object()


def _yaml_get(doc: dict, keys: list[str]) -> object:
    """Navigate a nested dict by key path. Returns _MISSING if not found."""
    node: object = doc
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return _MISSING
        node = node[key]
    return node


def _yaml_set(doc: dict, keys: list[str], value: object) -> None:
    """Set a value at a key path, creating intermediate dicts as needed."""
    node = doc
    for key in keys[:-1]:
        if key not in node or not isinstance(node.get(key), dict):
            node[key] = {}
        node = node[key]
    node[keys[-1]] = value


def _yaml_delete(doc: dict, keys: list[str]) -> bool:
    """Delete a key at a path. Returns True if deleted, False if not found."""
    node = doc
    for key in keys[:-1]:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    if isinstance(node, dict) and keys[-1] in node:
        del node[keys[-1]]
        return True
    return False
