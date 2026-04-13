"""Planning: build release plans, write dep pins."""

from __future__ import annotations

from pathlib import Path

from packaging.utils import canonicalize_name

from ..utils.config import get_config, get_publish_config
from ..context import ReleaseContext, RepositoryContext, build_context
from ..resolution import ReleaseResolution, resolve_release
from ..utils.shell import Progress
from ..models import (
    BuildStage,
    ChangedPackage,
    DownloadWheelsCommand,
    PackageInfo,
    PinDepsCommand,
    PlanConfig,
    PublishGithubReleaseCommand,
    PublishToIndexCommand,
    ReleasePlan,
    StageCommand,
    ShellCommand,
)
from ..utils.toml import read_pyproject

from ._graph import topo_layers
from ..utils.git import generate_release_notes
from ..utils.changes import detect_changes
from ..utils.dependencies import pin_dependencies, set_version
from ..utils.versions import (
    find_release_tags_below,
    parse_tag_version,
    strip_dev,
)


def _dist_name(name: str) -> str:
    """Convert a package name to its wheel/dist filename stem."""
    return canonicalize_name(name).replace("-", "_")


class ReleasePlanner:
    """Single entry point for creating release plans.

    Generates a ReleasePlan containing pre-computed shell commands for
    every phase (build, release, bump). The executor is a dumb runner.
    """

    def __init__(
        self,
        config: PlanConfig,
        ctx: RepositoryContext,
        *,
        progress: Progress | None = None,
    ) -> None:
        self.config = config
        self.ctx = ctx
        self.progress = progress

    def plan(self) -> ReleasePlan:
        """Detect changes and return a ReleasePlan."""
        packages = self.ctx.packages
        skip = frozenset(self.config.skip)

        # Step 1: Resolve baselines, release versions, and next versions
        # via the state machine. This also validates tag and version conflicts.
        if self.progress:
            self.progress.update("Resolving baselines")
        resolutions: dict[str, ReleaseResolution] = {}
        if isinstance(self.ctx, ReleaseContext):
            baselines = self.ctx.baselines
        else:
            baselines: dict[str, str | None] = {}
        for name, info in packages.items():
            r = resolve_release(
                info.version,
                name,
                self.ctx.repo,
                dev_release=self.config.dev_release,
                skip=skip,
            )
            resolutions[name] = r
            if not isinstance(self.ctx, ReleaseContext):
                baselines[name] = r.baseline_tag
        if self.progress:
            self.progress.complete(f"Resolved {len(packages)} baselines")

        # Step 2: Detect changes
        if self.progress:
            self.progress.update("Detecting changes")
        changed_names = detect_changes(
            packages,
            baselines,
            self.config.rebuild_all,
            rebuild=self.config.rebuild or None,
            ctx=self.ctx,
        )
        if self.config.restrict_packages and not self.config.rebuild_all:
            restrict_closure = self._collect_deps(
                set(self.config.restrict_packages), packages
            )
            changed_names = [n for n in changed_names if n in restrict_closure]
        raw_changed = {name: packages[name] for name in changed_names}
        unchanged = {
            name: info for name, info in packages.items() if name not in changed_names
        }
        if self.progress:
            self.progress.complete(
                f"Detected {len(changed_names)} changed, {len(unchanged)} unchanged"
            )

        # Step 3: Extract pre-computed versions from resolutions
        if self.progress:
            self.progress.update("Computing versions")
        current_versions = {name: info.version for name, info in raw_changed.items()}
        release_versions: dict[str, str] = {}
        next_versions: dict[str, str] = {}
        versioned: dict[str, PackageInfo] = {}
        for name, info in raw_changed.items():
            r = resolutions[name]
            release_versions[name] = r.release_version
            next_versions[name] = r.next_version
            versioned[name] = PackageInfo(
                path=info.path, version=r.release_version, deps=info.deps
            )

        # Find previous release tags for dep pinning
        if isinstance(self.ctx, ReleaseContext):
            release_tags = self.ctx.release_tags
        else:
            release_tags: dict[str, str | None] = {}
            for name, info in packages.items():
                tags = find_release_tags_below(
                    strip_dev(info.version), name, self.ctx.repo, limit=1
                )
                release_tags[name] = f"{name}/v{tags[0]}" if tags else None

        published_versions = self._published_versions(
            versioned, changed_names, packages, release_tags
        )
        if not self.config.dry_run:
            self._apply_versions_and_pins(versioned, published_versions)
        if self.progress:
            self.progress.complete(
                f"Computed versions for {len(changed_names)} packages"
            )

        # Step 4: Generate release note headers (hooks can customize via post_plan)
        if self.progress:
            self.progress.update("Generating release notes")
        notes: dict[str, str] = {}
        for name in changed_names:
            if name in self.config.release_notes:
                notes[name] = self.config.release_notes[name]
            else:
                notes[name] = generate_release_notes(name, versioned[name])
        if self.progress:
            self.progress.complete(f"Generated {len(notes)} release notes")

        # Determine which package gets "Latest" on GitHub
        root_doc = read_pyproject(Path.cwd() / "pyproject.toml")
        latest_pkg = get_config(root_doc).get("latest", "")

        # Assemble ChangedPackage objects
        changed: dict[str, ChangedPackage] = {}
        for name in sorted(changed_names):
            info = versioned[name]
            changed[name] = ChangedPackage(
                path=info.path,
                version=info.version,
                deps=info.deps,
                current_version=current_versions[name],
                release_version=release_versions[name],
                next_version=next_versions[name],
                last_release_tag=release_tags.get(name),
                baseline_tag=baselines.get(name),
                release_notes=notes.get(name, ""),
                make_latest=(name == latest_pkg) if latest_pkg else False,
                runners=self.config.matrix.get(name, [["ubuntu-latest"]]),
            )

        # Generate command sequences
        build_commands = self._generate_build_commands(changed, unchanged, release_tags)
        release_commands = self._generate_release_commands(changed)
        publish_config = get_publish_config(root_doc)
        publish_commands = self._generate_publish_commands(changed, publish_config)
        bump_commands = self._generate_bump_commands(changed, published_versions)

        return ReleasePlan(
            uvr_version=self.config.uvr_version,
            python_version=self.config.python_version,
            rebuild_all=self.config.rebuild_all,
            dev_release=self.config.dev_release,
            ci_publish=self.config.ci_publish,
            changed=changed,
            unchanged=unchanged,
            build_commands=build_commands,
            release_commands=release_commands,
            publish_commands=publish_commands,
            publish_environment=publish_config.get("environment", ""),
            bump_commands=bump_commands,
        )

    def _apply_versions_and_pins(
        self,
        changed: dict[str, PackageInfo],
        published_versions: dict[str, str],
    ) -> None:
        """Set release versions and pin deps in local pyproject.toml files."""
        for name, info in sorted(changed.items()):
            pyproject = Path(info.path) / "pyproject.toml"
            set_version(pyproject, info.version)

            dep_versions = {
                dep: published_versions[dep]
                for dep in info.deps
                if dep in published_versions
            }
            pin_dependencies(pyproject, dep_versions)

    # ------------------------------------------------------------------
    # Command generation
    # ------------------------------------------------------------------

    def _generate_build_commands(
        self,
        changed: dict[str, ChangedPackage],
        unchanged: dict[str, PackageInfo],
        release_tags: dict[str, str | None],
    ) -> dict[tuple[str, ...], list[BuildStage]]:
        """Generate build command stages per runner."""
        all_packages: dict[str, PackageInfo] = {**changed, **unchanged}

        # Build runner -> assigned packages mapping from ChangedPackage.runners
        by_runner: dict[tuple[str, ...], set[str]] = {}
        for name, pkg in changed.items():
            for runner in pkg.runners:
                key = tuple(runner)
                by_runner.setdefault(key, set()).add(name)

        result: dict[tuple[str, ...], list[BuildStage]] = {}
        for runner, assigned in sorted(by_runner.items()):
            stages: list[BuildStage] = []

            needed = self._collect_deps(assigned, all_packages)
            changed_to_build = {n: changed[n] for n in needed if n in changed}
            unchanged_deps = {n: unchanged[n] for n in needed if n in unchanged}

            # -- Stage 0: setup --
            setup_cmds: list[StageCommand] = [
                ShellCommand(
                    args=[
                        "uv",
                        "run",
                        "python",
                        "-c",
                        "from pathlib import Path; Path('dist').mkdir(exist_ok=True); Path('deps').mkdir(exist_ok=True)",
                    ],
                )
            ]

            # Fetch unchanged deps — single smart command handles run-id
            # fallback, transitive resolution, and caching.
            dep_tags: dict[str, str] = {}
            for name in sorted(unchanged_deps):
                tag = release_tags.get(name)
                if not tag:
                    msg = (
                        f"Cannot fetch unchanged dependency '{name}': "
                        f"no release tag found. Has it ever been released?"
                    )
                    raise ValueError(msg)
                dep_tags[name] = tag
            if dep_tags:
                setup_cmds.append(
                    DownloadWheelsCommand(
                        packages=dep_tags,
                        exclude=list(changed_to_build.keys()),
                        directory="deps",
                        label="Fetch unchanged dependencies",
                    )
                )
            stages.append(BuildStage(setup=setup_cmds))

            # -- Build stages: one per topo layer --
            layers = topo_layers(changed_to_build)
            max_layer = max(layers.values()) if layers else -1
            for layer in range(max_layer + 1):
                layer_cmds: dict[str, list[ShellCommand]] = {}
                for pkg, pkg_layer in sorted(layers.items()):
                    if pkg_layer != layer:
                        continue
                    info = changed_to_build[pkg]
                    build_args = [
                        "uv",
                        "build",
                        info.path,
                        "--out-dir",
                        "dist/",
                        "--find-links",
                        "dist/",
                        "--find-links",
                        "deps/",
                        "--no-sources",
                    ]
                    layer_cmds[pkg] = [
                        ShellCommand(args=build_args, label=f"Build {pkg}"),
                    ]
                stages.append(BuildStage(packages=layer_cmds))

            # -- Cleanup: remove transitive dep wheels --
            remove_patterns = [
                f"{_dist_name(pkg)}-*.whl"
                for pkg in sorted(changed_to_build)
                if pkg not in assigned
            ]
            if remove_patterns:
                globs = "; ".join(
                    f'[p.unlink() for p in Path("dist").glob("{pat}")]'
                    for pat in remove_patterns
                )
                stages.append(
                    BuildStage(
                        cleanup=[
                            ShellCommand(
                                args=[
                                    "uv",
                                    "run",
                                    "python",
                                    "-c",
                                    f"from pathlib import Path; {globs}",
                                ],
                                label="Remove transitive dep wheels",
                            )
                        ]
                    )
                )

            result[runner] = stages
        return result

    def _generate_release_commands(
        self,
        changed: dict[str, ChangedPackage],
    ) -> list[ShellCommand | PublishGithubReleaseCommand]:
        """Generate release commands: tag, create GitHub releases, push tags."""
        cmds: list[ShellCommand | PublishGithubReleaseCommand] = []

        # Release tags on the current commit (the "set release versions" commit)
        for name, pkg in sorted(changed.items()):
            tag = f"{name}/v{pkg.release_version}"
            cmds.append(ShellCommand(args=["git", "tag", tag], label=f"Tag {tag}"))

        # Create GitHub releases with wheels.
        # The --latest package is created last so GitHub doesn't auto-promote
        # a later release over it.
        release_order = sorted(
            changed.items(), key=lambda item: (item[1].make_latest is True, item[0])
        )
        for name, pkg in release_order:
            tag = f"{name}/v{pkg.release_version}"
            cmds.append(
                PublishGithubReleaseCommand(
                    tag=tag,
                    title=f"{name} {pkg.release_version}",
                    notes=pkg.release_notes,
                    dist_pattern=f"dist/{_dist_name(name)}-{pkg.release_version}-*.whl",
                    make_latest=pkg.make_latest,
                    label=f"Publish {tag}",
                )
            )

        # Push release tags (only after all releases succeed)
        cmds.append(
            ShellCommand(args=["git", "push", "--tags"], label="Push release tags")
        )

        return cmds

    def _generate_publish_commands(
        self,
        changed: dict[str, ChangedPackage],
        publish_config: dict,
    ) -> list[ShellCommand | PublishToIndexCommand]:
        """Generate publish commands for packages configured in [tool.uvr.publish]."""
        include = publish_config.get("include", [])
        exclude = publish_config.get("exclude", [])
        index = publish_config.get("index", "")
        trusted_publishing = publish_config.get("trusted_publishing", "automatic")

        # Determine which changed packages should be published
        publishable = set(changed.keys())
        if include:
            publishable &= set(include)
        publishable -= set(exclude)

        if not publishable:
            return []

        cmds: list[ShellCommand | PublishToIndexCommand] = []
        for name in sorted(publishable):
            pkg = changed[name]
            cmds.append(
                PublishToIndexCommand(
                    dist_pattern=f"dist/{_dist_name(name)}-{pkg.release_version}-*.whl",
                    index=index,
                    trusted_publishing=trusted_publishing,
                    label=f"Publish {name} {pkg.release_version} to index",
                )
            )
        return cmds

    def _generate_bump_commands(
        self,
        changed: dict[str, ChangedPackage],
        published_versions: dict[str, str],
    ) -> list[ShellCommand | PinDepsCommand]:
        """Generate bump commands (version bumps, commit, baseline tags, push)."""
        cmds: list[ShellCommand | PinDepsCommand] = []

        # Git identity (CI only)
        if self.config.ci_publish:
            cmds.append(
                ShellCommand(args=["git", "config", "user.name", "github-actions[bot]"])
            )
            cmds.append(
                ShellCommand(
                    args=[
                        "git",
                        "config",
                        "user.email",
                        "github-actions[bot]@users.noreply.github.com",
                    ]
                )
            )

        # Version bumps + dep pinning
        pyproject_paths: list[str] = []
        for name, pkg in sorted(changed.items()):
            pyproject = f"{pkg.path}/pyproject.toml"
            pyproject_paths.append(pyproject)

            cmds.append(
                ShellCommand(
                    args=["uv", "version", pkg.next_version, "--directory", pkg.path],
                    label=f"Bump {name} to {pkg.next_version}",
                )
            )

            dep_versions = {
                dep: published_versions[dep]
                for dep in pkg.deps
                if dep in published_versions
            }
            if dep_versions:
                cmds.append(
                    PinDepsCommand(
                        path=pyproject,
                        versions=dep_versions,
                        label=f"Pin {name} deps",
                    )
                )

        # Sync, stage, commit
        cmds.append(ShellCommand(args=["uv", "sync", "--all-groups", "--all-extras"]))
        for p in pyproject_paths:
            cmds.append(ShellCommand(args=["git", "add", p]))
        cmds.append(ShellCommand(args=["git", "add", "uv.lock"]))

        summary = "\n".join(
            f"  {n}: {pkg.release_version} -> {pkg.next_version}"
            for n, pkg in sorted(changed.items())
        )
        cmds.append(
            ShellCommand(
                args=[
                    "git",
                    "commit",
                    "-m",
                    "chore: prepare next release",
                    "-m",
                    summary,
                ]
            )
        )

        # Baseline tags
        for name, pkg in sorted(changed.items()):
            tag = f"{name}/v{pkg.next_version}-base"
            cmds.append(ShellCommand(args=["git", "tag", tag], label=f"Baseline {tag}"))

        # Push
        if self.config.ci_publish:
            cmds.append(ShellCommand(args=["git", "push"]))
            cmds.append(ShellCommand(args=["git", "push", "--tags"]))

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
                    parse_tag_version(tag) if tag and "/v" in tag else info.version
                )
        return versions

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


def build_plan(config: PlanConfig) -> ReleasePlan:
    """Run discovery locally and return a ReleasePlan."""
    ctx = build_context()
    return ReleasePlanner(config, ctx).plan()
