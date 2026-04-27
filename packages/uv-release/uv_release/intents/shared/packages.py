"""Shared commit message helpers used by multiple intents."""

from __future__ import annotations


def format_version_body(items: dict[str, str]) -> str:
    """Format a commit body listing package versions.

    Takes a dict of {package_name: version_string} and returns a sorted,
    newline-separated string of "name version" entries.
    """
    return "\n".join(f"{name} {version}" for name, version in sorted(items.items()))
