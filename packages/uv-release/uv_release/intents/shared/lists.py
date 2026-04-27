"""Shared list mutation helpers for configure intents."""

from __future__ import annotations


def apply_list_mutations(
    include: list[str],
    exclude: list[str],
    *,
    add_include: list[str],
    add_exclude: list[str],
    remove: list[str],
) -> tuple[list[str], list[str]]:
    """Apply add/remove mutations to include and exclude lists.

    Returns the mutated (include, exclude) pair.
    """
    for pkg in add_include:
        if pkg not in include:
            include.append(pkg)
    for pkg in add_exclude:
        if pkg not in exclude:
            exclude.append(pkg)
    for pkg in remove:
        if pkg in include:
            include.remove(pkg)
        if pkg in exclude:
            exclude.remove(pkg)
    return include, exclude
