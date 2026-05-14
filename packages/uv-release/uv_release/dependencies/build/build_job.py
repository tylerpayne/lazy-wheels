"""BuildJob: build changed packages."""

from __future__ import annotations

from diny import singleton, provider

from .build_order import BuildOrder
from .build_packages import BuildPackages
from ...commands import (
    AnyCommand,
    BuildCommand,
    DownloadWheelsCommand,
    MakeDirectoryCommand,
)
from ...types.job import Job
from ...types.package import Package
from .package_dependencies import PackageDependencies
from ..config.uvr_runners import UvrRunners
from ..params.reuse_run import ReuseRun
from ..params.skip_jobs import SkipJobs
from ..shared.github_repo import GitHubRepo


@singleton
class BuildJob(Job):
    """Build job for the release pipeline."""


@provider(BuildJob)
def provide_build_job(
    build_packages: BuildPackages,
    package_dependencies: PackageDependencies,
    build_order: BuildOrder,
    uvr_runners: UvrRunners,
    reuse_run: ReuseRun,
    skip_jobs: SkipJobs,
    github_repo: GitHubRepo,
) -> BuildJob:
    # Empty job if nothing to build, skipped by user, or reusing prior run.
    if not build_packages.items or "build" in skip_jobs.value or reuse_run.value:
        return BuildJob(name="build")

    commands: list[AnyCommand] = []

    # Ensure output dirs exist before --find-links tries to read them.
    commands.append(MakeDirectoryCommand(label="Create dist/", path="dist"))
    commands.append(MakeDirectoryCommand(label="Create deps/", path="deps"))

    for dep in package_dependencies.released:
        commands.append(
            DownloadWheelsCommand(
                label=f"Download {dep.package_name} wheels",
                tag_name=dep.tag_name,
                pattern="*.whl",
                output_dir="deps",
                repo=github_repo.name,
            )
        )

    targets = set(build_packages.items.keys())

    # Compute effective runners per package. A dep must build on every runner
    # where any of its dependents build, so the wheel is available locally via
    # --find-links. Walk layers in reverse (dependents first) to propagate.
    all_to_build = {
        item.name: item.package for layer in build_order.layers for item in layer
    }
    effective_runners = _compute_effective_runners(
        all_to_build,
        uvr_runners,
        build_packages,
    )

    for layer in build_order.layers:
        for item in layer:
            # target_runners = the runners where this is a release target (dist/).
            # On other runners it builds as a dep (deps/).
            own_runners = uvr_runners.items.get(item.name, [])
            target_r = own_runners if item.name in targets else []
            commands.append(
                BuildCommand(
                    label=f"Build {item.name}",
                    package_name=item.name,
                    package_path=item.package.path,
                    out_dir=item.out_dir,
                    runners=effective_runners.get(item.name, []),
                    target_runners=target_r,
                )
            )

    return BuildJob(name="build", commands=commands)


def _compute_effective_runners(
    all_to_build: dict[str, Package],
    uvr_runners: UvrRunners,
    build_packages: BuildPackages,
) -> dict[str, list[list[str]]]:
    """Compute which runners each package needs to build on.

    A target builds on its configured runners. A dep builds on the union of
    runners from all packages that depend on it, because those builds need
    the dep's wheel available locally via --find-links.
    """
    internal = set(all_to_build.keys())
    targets = set(build_packages.items.keys())

    # Start with each package's own configured runners. Targets without config
    # default to [["ubuntu-latest"]]. Deps start empty (they inherit from dependents).
    effective: dict[str, set[tuple[str, ...]]] = {}
    for name in all_to_build:
        if name in targets:
            pkg_runners = uvr_runners.items.get(name, [["ubuntu-latest"]])
            effective[name] = {tuple(r) for r in pkg_runners}
        else:
            effective[name] = set()

    # Propagate runners from each package to its internal deps.
    # Repeat until stable (handles transitive chains).
    changed = True
    while changed:
        changed = False
        for name, pkg in all_to_build.items():
            for dep in pkg.all_dep_names:
                if dep in internal and not effective[name] <= effective.get(dep, set()):
                    before = len(effective.get(dep, set()))
                    effective.setdefault(dep, set()).update(effective[name])
                    if len(effective[dep]) > before:
                        changed = True

    # Convert back to list form.
    return {
        name: [list(r) for r in sorted(runners)]
        for name, runners in effective.items()
        if runners
    }
