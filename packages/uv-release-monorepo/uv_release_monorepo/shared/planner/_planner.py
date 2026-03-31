"""Planning: build release plans, write dep pins."""

from __future__ import annotations

import re
from pathlib import Path

from packaging.utils import canonicalize_name

from ..utils.config import get_config
from ..context import ReleaseContext, RepositoryContext, build_context
from ..utils.shell import Progress
from ..models import (
    BuildStage,
    ChangedPackage,
    FetchGithubReleaseCommand,
    PackageInfo,
    PinDepsCommand,
    PlanConfig,
    PublishGithubReleaseCommand,
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
    bump_dev,
    bump_patch,
    detect_release_type_for_version,
    extract_pre_kind,
    find_previous_release,
    is_dev,
    is_post,
    is_pre,
    make_dev,
    make_post,
    make_pre,
    parse_tag_version,
    resolve_baseline,
    strip_dev,
)


def _dist_name(name: str) -> str:
    """Convert a package name to its wheel/dist filename stem."""
    return canonicalize_name(name).replace("-", "_")


def _next_dev_version(release_version: str) -> str:
    """Compute the next dev version after a release.

    Auto-detects from the release version:
    - ``1.0.1``       → ``1.0.2.dev0``   (stable → bump patch)
    - ``1.0.1a2``     → ``1.0.1a3.dev0`` (pre → increment pre number)
    - ``1.0.1.post0`` → ``1.0.1.post1.dev0`` (post → increment post number)
    """
    if is_pre(release_version):
        kind = extract_pre_kind(release_version)
        m = re.search(rf"{re.escape(kind)}(\d+)$", release_version)
        n = int(m.group(1)) + 1 if m else 1
        return make_dev(make_pre(release_version, kind, n))
    if is_post(release_version):
        m = re.search(r"\.post(\d+)$", release_version)
        n = int(m.group(1)) + 1 if m else 1
        return make_dev(make_post(release_version, n))
    return make_dev(bump_patch(release_version))


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

        # Step 1: Resolve baselines per release type
        if self.progress:
            self.progress.update("Resolving baselines")
        if isinstance(self.ctx, ReleaseContext):
            baselines = self.ctx.baselines
        else:
            baselines: dict[str, str | None] = {}
            for name, info in packages.items():
                rt = (
                    "dev"
                    if self.config.dev_release
                    else detect_release_type_for_version(info.version)
                )
                baselines[name] = resolve_baseline(
                    info.version,
                    rt,
                    name,
                    self.ctx.repo,
                )
        if self.progress:
            self.progress.complete(f"Resolved {len(packages)} baselines")

        # Step 2: Detect changes
        if self.progress:
            self.progress.update("Detecting changes")
        changed_names = detect_changes(
            packages, baselines, self.config.rebuild_all, ctx=self.ctx
        )
        raw_changed = {name: packages[name] for name in changed_names}
        unchanged = {
            name: info for name, info in packages.items() if name not in changed_names
        }
        if self.progress:
            self.progress.complete(
                f"Detected {len(changed_names)} changed, {len(unchanged)} unchanged"
            )

        # Step 3: Compute release versions
        if self.progress:
            self.progress.update("Computing versions")
        current_versions = {name: info.version for name, info in raw_changed.items()}
        release_versions = self._compute_release_versions(raw_changed)
        versioned: dict[str, PackageInfo] = {}
        for name, info in raw_changed.items():
            versioned[name] = PackageInfo(
                path=info.path, version=release_versions[name], deps=info.deps
            )

        # Find previous release tags for dep pinning
        if isinstance(self.ctx, ReleaseContext):
            release_tags = self.ctx.release_tags
        else:
            release_tags: dict[str, str | None] = {}
            for name, info in packages.items():
                prev = find_previous_release(info.version, name, self.ctx.repo)
                release_tags[name] = f"{name}/v{prev}" if prev else None

        published_versions = self._published_versions(
            versioned, changed_names, packages, release_tags
        )
        if not self.config.dry_run:
            self._apply_versions_and_pins(versioned, published_versions)
        next_versions = self._compute_next_versions(versioned)
        if self.progress:
            self.progress.complete(
                f"Computed versions for {len(changed_names)} packages"
            )

        # Step 4: Generate release note headers (hooks can customize via post_plan)
        if self.progress:
            self.progress.update("Generating release notes")
        notes: dict[str, str] = {}
        for name in changed_names:
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
                release_notes=notes.get(name, ""),
                make_latest=name == latest_pkg,
                runners=self.config.matrix.get(name, [["ubuntu-latest"]]),
            )

        # Generate command sequences
        build_commands = self._generate_build_commands(changed, unchanged, release_tags)
        release_commands = self._generate_release_commands(changed)
        bump_commands = self._generate_bump_commands(changed, published_versions)

        # Validate tag conflicts: always abort on conflict
        self._check_tag_conflicts(changed)

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

    def _compute_release_versions(
        self,
        changed: dict[str, PackageInfo],
    ) -> dict[str, str]:
        """Compute the release version string for each changed package."""
        result: dict[str, str] = {}

        if self.config.dev_release:
            for name, info in changed.items():
                # If already dev, publish as-is; otherwise append .dev0
                result[name] = (
                    info.version if is_dev(info.version) else make_dev(info.version)
                )
        else:
            # Default: strip .devN, release whatever is underneath
            for name, info in changed.items():
                result[name] = strip_dev(info.version)

        return result

    def _compute_next_versions(self, changed: dict[str, PackageInfo]) -> dict[str, str]:
        """Compute the post-release dev version for each changed package."""
        result: dict[str, str] = {}

        for name, info in changed.items():
            if self.config.dev_release:
                result[name] = bump_dev(info.version)
            else:
                # Auto-detect from the release version
                result[name] = _next_dev_version(info.version)

        return result

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

            for name in sorted(unchanged_deps):
                tag = release_tags.get(name)
                if tag:
                    setup_cmds.append(
                        FetchGithubReleaseCommand(
                            tag=tag,
                            dist_name=_dist_name(name),
                            directory="deps",
                            label=f"Fetch {name} from {tag}",
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

        # Create GitHub releases with wheels
        for name, pkg in sorted(changed.items()):
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

    def _find_tag_conflicts(
        self,
        changed: dict[str, ChangedPackage],
    ) -> list[str]:
        """Find planned tags that already exist locally.

        Returns a list of conflicting tag names. Does not abort.
        """
        repo = self.ctx.repo
        conflicts: list[str] = []
        for name, pkg in changed.items():
            for tag in (
                f"{name}/v{pkg.release_version}",
                f"{name}/v{pkg.next_version}-base",
            ):
                if repo.references.get(f"refs/tags/{tag}") is not None:
                    conflicts.append(tag)
        return conflicts

    def _check_tag_conflicts(
        self,
        changed: dict[str, ChangedPackage],
    ) -> None:
        """Verify that no planned tags conflict. Aborts on conflict."""
        from ..utils.shell import exit_fatal

        conflicts = self._find_tag_conflicts(changed)
        if not conflicts:
            return

        lines = "\n".join(f"  {t}" for t in sorted(conflicts))
        post_hint = "  1. Use --post to publish a post-release\n"
        bump_cmds = []
        for t in conflicts:
            pkg_name = t.split("/v")[0]
            if pkg_name in changed:
                ver = parse_tag_version(t)
                try:
                    next_ver = make_dev(bump_patch(ver))
                    bump_cmds.append(
                        f"     uv version {next_ver} --directory {changed[pkg_name].path}"
                    )
                except ValueError:
                    bump_cmds.append(
                        f"     uv version <next-version> --directory {changed[pkg_name].path}"
                    )

        bump_hint = ""
        if bump_cmds:
            bump_detail = "\n".join(bump_cmds)
            bump_hint = f"  2. Bump past the conflict:\n{bump_detail}\n"
        else:
            bump_hint = "  2. Bump to a new version: uv version <new-version> --directory <pkg>\n"

        exit_fatal(
            f"These tags/releases already exist and would conflict:\n"
            f"{lines}\n\n"
            f"To resolve, either:\n"
            f"{post_hint}"
            f"{bump_hint}"
        )

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
