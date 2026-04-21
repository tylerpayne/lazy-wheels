"""Shared job builders used by multiple intents."""

from __future__ import annotations

from collections import defaultdict

from ...commands import (
    BuildCommand,
    DownloadWheelsCommand,
    MakeDirectoryCommand,
    ShellCommand,
)
from ...graph import topo_layers
from ...states.release_tags import ReleaseTags
from ...states.workspace import Workspace
from ...types import Command, Job, Package, Release


def compute_build_job(
    workspace: Workspace,
    releases: dict[str, Release],
    release_tags: ReleaseTags,
    runners: dict[str, list[list[str]]],
) -> Job:
    """Build job with layered stages and unchanged-dep fetching."""
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

    dep_tag_map: dict[str, str] = {}
    dep_packages: list[Package] = []
    for name, pkg in workspace.packages.items():
        if name in releases:
            continue
        tag = release_tags.tags.get(name)
        if tag:
            dep_tag_map[name] = tag
            dep_packages.append(pkg)
    if dep_packages:
        commands.append(
            DownloadWheelsCommand(
                label="Fetch unchanged dependencies",
                packages=dep_packages,
                release_tags=dep_tag_map,
            )
        )

    for layer_idx in sorted(by_layer.keys()):
        for pkg_name in sorted(by_layer[layer_idx]):
            release = releases[pkg_name]
            pkg_runners = runners.get(pkg_name, [])
            commands.append(
                BuildCommand(
                    label=f"Build {pkg_name} (layer {layer_idx})",
                    package=release.package,
                    runners=pkg_runners,
                )
            )

    return Job(name="build", commands=commands)


def compute_download_commands(*, reuse_run: str = "") -> list[Command]:
    """Commands to download built wheels from current or prior CI run."""
    commands: list[Command] = [
        MakeDirectoryCommand(label="Create dist directory", path="dist"),
    ]

    if reuse_run:
        commands.append(
            ShellCommand(
                label=f"Download artifacts from run {reuse_run}",
                args=["gh", "run", "download", reuse_run, "--dir", "dist"],
            )
        )
    else:
        commands.append(
            ShellCommand(
                label="Download build artifacts",
                args=["bash", "-c", 'gh run download "$RUN_ID" --dir dist'],
            )
        )

    commands.append(
        ShellCommand(
            label="Flatten artifact directories",
            args=[
                "bash",
                "-c",
                'find dist -mindepth 2 -name "*.whl" -exec mv {} dist/ \\;',
            ],
        )
    )

    return commands
