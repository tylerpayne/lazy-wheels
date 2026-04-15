"""Generate build jobs with layered stages per runner."""

from __future__ import annotations

from collections import defaultdict

from ..commands import BuildCommand, DownloadWheelsCommand, ShellCommand
from ..graph import topo_layers
from ..types import Command, Job, Package, Release, Tag, Workspace


def plan_build_job(
    workspace: Workspace,
    releases: dict[str, Release],
) -> Job:
    """Generate build job with layered stages per runner."""
    if not releases:
        return Job(name="build")

    release_packages = {name: releases[name].package for name in releases}
    layers = topo_layers(release_packages)

    by_layer: dict[int, list[str]] = defaultdict(list)
    for name, layer in layers.items():
        by_layer[layer].append(name)

    commands: list[Command] = []

    commands.append(
        ShellCommand(
            label="Create build directories", args=["mkdir", "-p", "dist", "deps"]
        )
    )

    dep_tags: dict[str, str] = {}
    dep_packages: list[Package] = []
    for name, pkg in workspace.packages.items():
        if name in releases:
            continue
        tag = _find_release_tag(name, pkg)
        if tag:
            dep_tags[name] = tag
            dep_packages.append(pkg)
    if dep_packages:
        commands.append(
            DownloadWheelsCommand(
                label="Fetch unchanged dependencies",
                packages=dep_packages,
                release_tags=dep_tags,
            )
        )

    for layer_idx in sorted(by_layer.keys()):
        for pkg_name in sorted(by_layer[layer_idx]):
            release = releases[pkg_name]
            pkg_runners = workspace.runners.get(pkg_name, [])
            commands.append(
                BuildCommand(
                    label=f"Build {pkg_name} (layer {layer_idx})",
                    package=release.package,
                    runners=pkg_runners,
                )
            )

    return Job(name="build", commands=commands)


def _find_release_tag(name: str, pkg: Package) -> str | None:
    """Find the release tag name for an unchanged package's current version."""
    if pkg.version.is_dev:
        return None
    return Tag.release_tag_name(name, pkg.version)
