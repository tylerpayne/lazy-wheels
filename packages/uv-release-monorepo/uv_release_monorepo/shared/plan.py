"""Planning: build release plans, write dep pins."""

from __future__ import annotations

import subprocess
from pathlib import Path

from packaging.utils import canonicalize_name

from .deps import update_dep_pins
from .graph import topo_sort
from .models import (
    BumpPlan,
    DepPinChange,
    MatrixEntry,
    PackageInfo,
    PinChange,
    PlanCommand,
    PlanConfig,
    PublishEntry,
    ReleasePlan,
)
from .toml import get_uvr_config, load_pyproject
from .versions import bump_patch, make_dev, strip_dev, version_from_tag
from .changes import detect_changes
from .discovery import discover_packages, find_release_tags, get_baseline_tags
from .publish import generate_release_notes


class ReleasePlanner:
    """Single entry point for creating release plans.

    Generates a ReleasePlan containing pre-computed shell commands for
    every phase (build, publish, finalize). The executor is a dumb runner.
    """

    def __init__(self, config: PlanConfig) -> None:
        self.config = config

    def plan(self) -> tuple[ReleasePlan, list[PinChange]]:
        """Discover packages, detect changes, return a ReleasePlan."""
        packages = discover_packages()
        release_tags = find_release_tags(packages)
        baselines = get_baseline_tags(packages)
        changed_names = detect_changes(packages, baselines, self.config.rebuild_all)

        changed = {name: packages[name] for name in changed_names}
        unchanged = {
            name: info for name, info in packages.items() if name not in changed_names
        }

        # Strip .dev suffixes — the plan stores clean release versions.
        for name, info in changed.items():
            changed[name] = PackageInfo(
                path=info.path, version=strip_dev(info.version), deps=info.deps
            )

        # Compute published versions for internal dep pinning
        published_versions = self._published_versions(
            changed, changed_names, packages, release_tags
        )

        # Check dep pins without writing
        pin_changes = self._detect_pin_changes(
            changed_names, packages, published_versions
        )

        # Pre-compute version bumps
        bumps: dict[str, BumpPlan] = {}
        for name in changed_names:
            bumps[name] = BumpPlan(new_version=bump_patch(changed[name].version))

        # Expand matrix
        matrix_entries = self._expand_matrix(changed_names, changed)
        unique_runners = sorted(set(e.runner for e in matrix_entries))

        # Build publish matrix
        publish_entries = self._build_publish_matrix(
            changed_names, changed, release_tags
        )

        # Generate command sequences
        build_commands = self._generate_build_commands(
            changed, unchanged, release_tags, matrix_entries
        )
        publish_commands = self._generate_publish_commands(changed, release_tags)
        finalize_commands = self._generate_finalize_commands(
            changed, bumps, published_versions
        )

        result_plan = ReleasePlan(
            uvr_version=self.config.uvr_version,
            python_version=self.config.python_version,
            rebuild_all=self.config.rebuild_all,
            changed=changed,
            unchanged=unchanged,
            release_tags=release_tags,
            matrix=matrix_entries,
            runners=unique_runners,
            bumps=bumps,
            publish_matrix=publish_entries,
            ci_publish=self.config.ci_publish,
            build_commands=build_commands,
            publish_commands=publish_commands,
            finalize_commands=finalize_commands,
        )
        return result_plan, pin_changes

    # ------------------------------------------------------------------
    # Command generation
    # ------------------------------------------------------------------

    def _generate_build_commands(
        self,
        changed: dict[str, PackageInfo],
        unchanged: dict[str, PackageInfo],
        release_tags: dict[str, str | None],
        matrix_entries: list[MatrixEntry],
    ) -> dict[str, list[PlanCommand]]:
        """Generate build commands per runner."""
        all_packages = {**changed, **unchanged}
        by_runner: dict[str, set[str]] = {}
        for entry in matrix_entries:
            by_runner.setdefault(entry.runner, set()).add(entry.package)

        result: dict[str, list[PlanCommand]] = {}
        for runner, assigned in sorted(by_runner.items()):
            cmds: list[PlanCommand] = []
            cmds.append(PlanCommand(args=["mkdir", "-p", "dist"]))

            # Collect transitive deps
            needed = self._collect_deps(assigned, all_packages)
            changed_to_build = {n: changed[n] for n in needed if n in changed}
            unchanged_deps = {n: unchanged[n] for n in needed if n in unchanged}

            # Fetch unchanged dep wheels
            for name in sorted(unchanged_deps):
                tag = release_tags.get(name)
                if tag:
                    wheel_name = canonicalize_name(name).replace("-", "_")
                    cmds.append(
                        PlanCommand(
                            args=[
                                "gh",
                                "release",
                                "download",
                                tag,
                                "--pattern",
                                f"{wheel_name}-*.whl",
                                "--dir",
                                "dist/",
                                "--clobber",
                            ],
                            label=f"Fetch {name} from {tag}",
                            check=False,
                        )
                    )

            # Build changed packages in topo order
            build_order = topo_sort(changed_to_build)
            for pkg in build_order:
                info = changed_to_build[pkg]
                release_ver = strip_dev(info.version)
                cmds.append(
                    PlanCommand(
                        args=[
                            "uvr",
                            "set-version",
                            "--path",
                            f"{info.path}/pyproject.toml",
                            "--version",
                            release_ver,
                        ],
                        label=f"Set {pkg} version to {release_ver}",
                    )
                )
                cmds.append(
                    PlanCommand(
                        args=[
                            "uv",
                            "build",
                            info.path,
                            "--out-dir",
                            "dist/",
                            "--find-links",
                            "dist/",
                        ],
                        label=f"Build {pkg}",
                    )
                )

            # Remove wheels for packages not assigned to this runner
            for pkg in sorted(set(changed_to_build) | set(unchanged_deps)):
                if pkg not in assigned:
                    dist_name = canonicalize_name(pkg).replace("-", "_")
                    cmds.append(
                        PlanCommand(
                            args=[
                                "find",
                                "dist",
                                "-name",
                                f"{dist_name}-*.whl",
                                "-delete",
                            ],
                            label=f"Remove transitive dep wheel {pkg}",
                            check=False,
                        )
                    )

            result[runner] = cmds
        return result

    def _generate_publish_commands(
        self,
        changed: dict[str, PackageInfo],
        release_tags: dict[str, str | None],
    ) -> list[PlanCommand]:
        """Generate publish commands (only for local execution)."""
        if self.config.ci_publish:
            return []

        cmds: list[PlanCommand] = []
        for name, info in sorted(changed.items()):
            tag = f"{name}/v{info.version}"
            dist_name = canonicalize_name(name).replace("-", "_")
            baseline = release_tags.get(name)
            notes = generate_release_notes(name, info, baseline)
            cmds.append(
                PlanCommand(
                    args=[
                        "gh",
                        "release",
                        "create",
                        tag,
                        "--title",
                        f"{name} {info.version}",
                        "--notes",
                        notes,
                        "--pattern",
                        f"dist/{dist_name}-{info.version}-*.whl",
                    ],
                    label=f"Publish {tag}",
                )
            )
        return cmds

    def _generate_finalize_commands(
        self,
        changed: dict[str, PackageInfo],
        bumps: dict[str, BumpPlan],
        published_versions: dict[str, str],
    ) -> list[PlanCommand]:
        """Generate finalize commands (tag, bump, commit, push)."""
        cmds: list[PlanCommand] = []

        # Git identity (CI only)
        if self.config.ci_publish:
            cmds.append(
                PlanCommand(
                    args=["git", "config", "user.name", "github-actions[bot]"],
                )
            )
            cmds.append(
                PlanCommand(
                    args=[
                        "git",
                        "config",
                        "user.email",
                        "github-actions[bot]@users.noreply.github.com",
                    ],
                )
            )

        # Release tags (local only — CI publish action creates them)
        if not self.config.ci_publish:
            for name, info in sorted(changed.items()):
                tag = f"{name}/v{info.version}"
                cmds.append(
                    PlanCommand(
                        args=["git", "tag", tag],
                        label=f"Tag {tag}",
                    )
                )

        # Version bumps + dep pinning
        pyproject_paths: list[str] = []
        for name, bump in sorted(bumps.items()):
            info = changed[name]
            dev_version = make_dev(bump.new_version)
            pyproject = f"{info.path}/pyproject.toml"
            pyproject_paths.append(pyproject)

            cmds.append(
                PlanCommand(
                    args=[
                        "uvr",
                        "set-version",
                        "--path",
                        pyproject,
                        "--version",
                        dev_version,
                    ],
                    label=f"Bump {name} to {dev_version}",
                )
            )

            # Pin internal deps to just-published versions
            dep_specs = [
                f"{dep}>={published_versions[dep]}"
                for dep in info.deps
                if dep in published_versions
            ]
            if dep_specs:
                cmds.append(
                    PlanCommand(
                        args=["uvr", "pin-deps", "--path", pyproject] + dep_specs,
                        label=f"Pin {name} deps",
                    )
                )

        # Sync, stage, commit
        cmds.append(
            PlanCommand(
                args=["uv", "sync", "--all-groups", "--all-extras"],
            )
        )
        for p in pyproject_paths:
            cmds.append(PlanCommand(args=["git", "add", p]))
        cmds.append(PlanCommand(args=["git", "add", "uv.lock"]))

        summary = "\n".join(
            f"  {n}: {changed[n].version} -> {b.new_version}"
            for n, b in sorted(bumps.items())
        )
        cmds.append(
            PlanCommand(
                args=[
                    "git",
                    "commit",
                    "-m",
                    "chore: prepare next release",
                    "-m",
                    summary,
                ],
            )
        )

        # Baseline tags
        for name, bump in sorted(bumps.items()):
            tag = f"{name}/v{bump.new_version}-base"
            cmds.append(
                PlanCommand(
                    args=["git", "tag", tag],
                    label=f"Baseline {tag}",
                )
            )

        # Push
        if self.config.ci_publish:
            cmds.append(PlanCommand(args=["git", "push"]))
            cmds.append(PlanCommand(args=["git", "push", "--tags"]))

        return cmds

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _published_versions(
        changed: dict[str, PackageInfo],
        changed_names: list[str] | set[str],
        packages: dict[str, PackageInfo],
        release_tags: dict[str, str | None],
    ) -> dict[str, str]:
        versions: dict[str, str] = {}
        for name in changed_names:
            versions[name] = changed[name].version
        for name, info in packages.items():
            if name not in changed_names:
                tag = release_tags.get(name)
                versions[name] = (
                    version_from_tag(tag) if tag and "/v" in tag else info.version
                )
        return versions

    def _detect_pin_changes(
        self,
        changed_names: list[str] | set[str],
        packages: dict[str, PackageInfo],
        published_versions: dict[str, str],
    ) -> list[PinChange]:
        pin_changes: list[PinChange] = []
        for name in changed_names:
            info = packages[name]
            dep_versions = {
                dep: published_versions[dep]
                for dep in info.deps
                if dep in published_versions
            }
            changes = update_dep_pins(
                Path(info.path) / "pyproject.toml", dep_versions, write=False
            )
            if changes:
                pin_changes.append(
                    PinChange(
                        package=name,
                        changes=[
                            DepPinChange(old_spec=old, new_spec=new)
                            for old, new in changes
                        ],
                    )
                )
        return pin_changes

    def _expand_matrix(
        self,
        changed_names: list[str] | set[str],
        changed: dict[str, PackageInfo],
    ) -> list[MatrixEntry]:
        entries: list[MatrixEntry] = []
        for name in sorted(changed_names):
            info = changed[name]
            runners = self.config.matrix.get(name, ["ubuntu-latest"])
            for runner in runners:
                entries.append(
                    MatrixEntry(
                        package=name,
                        runner=runner,
                        path=info.path,
                        version=info.version,
                    )
                )
        return entries

    def _build_publish_matrix(
        self,
        changed_names: list[str] | set[str],
        changed: dict[str, PackageInfo],
        release_tags: dict[str, str | None],
    ) -> list[PublishEntry]:
        root_doc = load_pyproject(Path.cwd() / "pyproject.toml")
        latest_pkg = get_uvr_config(root_doc).get("latest", "")
        entries: list[PublishEntry] = []
        for name in sorted(changed_names):
            info = changed[name]
            baseline = release_tags.get(name)
            entries.append(
                PublishEntry(
                    package=name,
                    version=info.version,
                    tag=f"{name}/v{info.version}",
                    title=f"{name} {info.version}",
                    body=generate_release_notes(name, info, baseline),
                    make_latest=name == latest_pkg,
                    dist_name=canonicalize_name(name).replace("-", "_"),
                )
            )
        return entries

    @staticmethod
    def _collect_deps(
        names: set[str], all_packages: dict[str, PackageInfo]
    ) -> set[str]:
        visited: set[str] = set()
        queue = list(names)
        while queue:
            pkg = queue.pop()
            if pkg in visited:
                continue
            visited.add(pkg)
            if pkg in all_packages:
                for dep in all_packages[pkg].deps:
                    if dep in all_packages and dep not in visited:
                        queue.append(dep)
        return visited


# Keep build_plan as a thin wrapper for backward compatibility
def build_plan(config: PlanConfig) -> tuple[ReleasePlan, list[PinChange]]:
    """Run discovery locally and return a ReleasePlan and pin change details."""
    return ReleasePlanner(config).plan()


def write_dep_pins(plan: ReleasePlan) -> list[PinChange]:
    """Write pending dep pin updates via ``uv add --package PKG --frozen DEP>=VER``."""
    published_versions: dict[str, str] = {}
    for name, info in plan.changed.items():
        published_versions[name] = info.version
    for name in plan.unchanged:
        tag = plan.release_tags.get(name)
        published_versions[name] = (
            version_from_tag(tag)
            if tag and "/v" in tag
            else plan.unchanged[name].version
        )

    result: list[PinChange] = []
    for name, info in plan.changed.items():
        dep_versions = {
            dep: published_versions[dep]
            for dep in info.deps
            if dep in published_versions
        }
        changes = update_dep_pins(
            Path(info.path) / "pyproject.toml", dep_versions, write=False
        )
        if changes:
            result.append(
                PinChange(
                    package=name,
                    changes=[
                        DepPinChange(old_spec=old, new_spec=new) for old, new in changes
                    ],
                )
            )

    for pin_change in result:
        for dep_change in pin_change.changes:
            cmd = [
                "uv",
                "add",
                "--package",
                pin_change.package,
                "--frozen",
                dep_change.new_spec,
            ]
            subprocess.run(cmd, check=True)

    return result
