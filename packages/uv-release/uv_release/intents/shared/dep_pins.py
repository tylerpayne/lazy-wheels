"""Shared dependency-pinning logic used by multiple intents."""

from __future__ import annotations

from collections.abc import Iterable

from ...commands import PinDepsCommand
from ...types import Package


def compute_dep_pins(
    packages: Iterable[Package],
    version_map: dict[str, Package],
) -> list[PinDepsCommand]:
    """Build PinDepsCommands for packages whose deps appear in version_map.

    For each package in *packages*, checks whether any of its declared
    dependencies appear in *version_map* (a mapping of package name to
    Package with the target version). If so, emits a PinDepsCommand.
    """
    commands: list[PinDepsCommand] = []
    for pkg in packages:
        pins = {dep: version_map[dep] for dep in pkg.dependencies if dep in version_map}
        if pins:
            commands.append(
                PinDepsCommand(
                    label=f"Pin deps for {pkg.name}",
                    package=pkg,
                    pins=pins,
                )
            )
    return commands
