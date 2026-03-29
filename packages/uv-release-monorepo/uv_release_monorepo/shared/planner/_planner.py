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
    PackageInfo,
    PlanCommand,
    PlanConfig,
    ReleasePlan,
)
from ..utils.toml import read_pyproject

from ._graph import topo_layers
from ..utils.git import generate_release_notes
from ..utils.changes import detect_changes
from ..utils.dependencies import pin_dependencies, set_version
from ..utils.versions import (
    bump_dev,
    bump_patch,
    find_previous_release,
    get_base_version,
    is_dev,
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


class ReleasePlanner:
    """Single entry point for creating release plans.

    Generates a ReleasePlan containing pre-computed shell commands for
    every phase (build, publish, finalize). The executor is a dumb runner.
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
                baselines[name] = resolve_baseline(
                    info.version,
                    self.config.release_type,
                    self.config.pre_kind,
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
                try:
                    prev = find_previous_release(info.version, name, self.ctx.repo)
                    release_tags[name] = f"{name}/v{prev}" if prev else None
                except ValueError:
                    release_tags[name] = None

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

        # Step 4: Generate release notes
        if self.progress:
            self.progress.update("Generating release notes")
        notes: dict[str, str] = {}
        for name in changed_names:
            info = versioned[name]
            version = (
                get_base_version(info.version) if is_pre(info.version) else info.version
            )
            prev = find_previous_release(version, name, self.ctx.repo)
            prev_tag = f"{name}/v{prev}" if prev else None
            notes[name] = generate_release_notes(
                name, info, prev_tag, repo=self.ctx.repo
            )
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
        finalize_commands = self._generate_finalize_commands(
            changed, published_versions
        )

        # Validate no tag conflicts (uses targeted GitHub API checks)
        self._check_tag_conflicts(changed)

        return ReleasePlan(
            uvr_version=self.config.uvr_version,
            python_version=self.config.python_version,
            rebuild_all=self.config.rebuild_all,
            release_type=self.config.release_type,
            ci_publish=self.config.ci_publish,
            changed=changed,
            unchanged=unchanged,
            build_commands=build_commands,
            release_commands=release_commands,
            finalize_commands=finalize_commands,
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
        rt = self.config.release_type
        result: dict[str, str] = {}

        if rt == "dev":
            for name, info in changed.items():
                # If already dev, publish as-is; otherwise append .dev0
                result[name] = (
                    info.version if is_dev(info.version) else make_dev(info.version)
                )
        elif rt == "pre":
            kind = self.config.pre_kind
            for name, info in changed.items():
                without_dev = strip_dev(info.version)
                # If already the right kind (e.g. version is 1.0.1b2.dev0
                # and --pre b), strip dev → 1.0.1b2
                if re.search(rf"{re.escape(kind)}\d+$", without_dev):
                    result[name] = without_dev
                else:
                    # Different kind or no pre suffix — start at kind0
                    # e.g. 1.0.1a6.dev0 + --pre b → 1.0.1b0
                    result[name] = f"{get_base_version(info.version)}{kind}0"
        elif rt == "post":
            for name, info in changed.items():
                # Strip .devN → release the post-release version as-is
                # e.g. 1.0.1.post0.dev0 → 1.0.1.post0
                result[name] = strip_dev(info.version)
        else:
            for name, info in changed.items():
                result[name] = get_base_version(info.version)

        return result

    def _compute_next_versions(self, changed: dict[str, PackageInfo]) -> dict[str, str]:
        """Compute the post-release dev version for each changed package."""
        rt = self.config.release_type
        result: dict[str, str] = {}

        for name, info in changed.items():
            if rt == "dev":
                result[name] = bump_dev(info.version)
            elif rt == "pre":
                kind = self.config.pre_kind
                m = re.search(rf"{re.escape(kind)}(\d+)$", info.version)
                n = int(m.group(1)) + 1 if m else 1
                result[name] = make_dev(make_pre(info.version, kind, n))
            elif rt == "post":
                m = re.search(r"\.post(\d+)$", info.version)
                n = int(m.group(1)) + 1 if m else 1
                result[name] = make_dev(make_post(info.version, n))
            else:
                result[name] = make_dev(bump_patch(info.version))

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
            setup_cmds: list[PlanCommand] = [
                PlanCommand(
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
                        PlanCommand(
                            args=[
                                "gh",
                                "release",
                                "download",
                                tag,
                                "--pattern",
                                f"{_dist_name(name)}-*.whl",
                                "--dir",
                                "deps/",
                                "--clobber",
                            ],
                            label=f"Fetch {name} from {tag}",
                            check=False,
                        )
                    )
            stages.append(BuildStage(setup=setup_cmds))

            # -- Build stages: one per topo layer --
            layers = topo_layers(changed_to_build)
            max_layer = max(layers.values()) if layers else -1
            for layer in range(max_layer + 1):
                layer_cmds: dict[str, list[PlanCommand]] = {}
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
                    ]
                    if layer > 0:
                        build_args.append("--no-sources")
                    layer_cmds[pkg] = [
                        PlanCommand(args=build_args, label=f"Build {pkg}"),
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
                            PlanCommand(
                                args=[
                                    "uv",
                                    "run",
                                    "python",
                                    "-c",
                                    f"from pathlib import Path; {globs}",
                                ],
                                label="Remove transitive dep wheels",
                                check=False,
                            )
                        ]
                    )
                )

            result[runner] = stages
        return result

    def _generate_release_commands(
        self,
        changed: dict[str, ChangedPackage],
    ) -> list[PlanCommand]:
        """Generate publish commands (only for local execution)."""
        if self.config.ci_publish:
            return []

        cmds: list[PlanCommand] = []
        for name, pkg in sorted(changed.items()):
            tag = f"{name}/v{pkg.release_version}"
            cmds.append(
                PlanCommand(
                    args=[
                        "gh",
                        "release",
                        "create",
                        tag,
                        "--title",
                        f"{name} {pkg.release_version}",
                        "--notes",
                        pkg.release_notes,
                        "--pattern",
                        f"dist/{_dist_name(name)}-{pkg.release_version}-*.whl",
                    ],
                    label=f"Publish {tag}",
                )
            )
        return cmds

    def _generate_finalize_commands(
        self,
        changed: dict[str, ChangedPackage],
        published_versions: dict[str, str],
    ) -> list[PlanCommand]:
        """Generate finalize commands (tag, bump, commit, push)."""
        cmds: list[PlanCommand] = []

        # Git identity (CI only)
        if self.config.ci_publish:
            cmds.append(
                PlanCommand(args=["git", "config", "user.name", "github-actions[bot]"])
            )
            cmds.append(
                PlanCommand(
                    args=[
                        "git",
                        "config",
                        "user.email",
                        "github-actions[bot]@users.noreply.github.com",
                    ]
                )
            )

        # Release tags (local only -- CI publish action creates them)
        if not self.config.ci_publish:
            for name, pkg in sorted(changed.items()):
                tag = f"{name}/v{pkg.release_version}"
                cmds.append(PlanCommand(args=["git", "tag", tag], label=f"Tag {tag}"))

        # Version bumps + dep pinning
        pyproject_paths: list[str] = []
        for name, pkg in sorted(changed.items()):
            pyproject = f"{pkg.path}/pyproject.toml"
            pyproject_paths.append(pyproject)

            cmds.append(
                PlanCommand(
                    args=["uv", "version", pkg.next_version, "--directory", pkg.path],
                    label=f"Bump {name} to {pkg.next_version}",
                )
            )

            dep_specs = [
                f"{dep}>={published_versions[dep]}"
                for dep in pkg.deps
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
        cmds.append(PlanCommand(args=["uv", "sync", "--all-groups", "--all-extras"]))
        for p in pyproject_paths:
            cmds.append(PlanCommand(args=["git", "add", p]))
        cmds.append(PlanCommand(args=["git", "add", "uv.lock"]))

        summary = "\n".join(
            f"  {n}: {pkg.release_version} -> {pkg.next_version}"
            for n, pkg in sorted(changed.items())
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
                ]
            )
        )

        # Baseline tags
        for name, pkg in sorted(changed.items()):
            tag = f"{name}/v{pkg.next_version}-base"
            cmds.append(PlanCommand(args=["git", "tag", tag], label=f"Baseline {tag}"))

        # Push
        if self.config.ci_publish:
            cmds.append(PlanCommand(args=["git", "push"]))
            cmds.append(PlanCommand(args=["git", "push", "--tags"]))

        return cmds

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_tag_conflicts(
        self,
        changed: dict[str, ChangedPackage],
    ) -> None:
        """Verify that no planned tags already exist locally or as GitHub releases.

        Checks local git refs first (free), then makes targeted GitHub API
        calls only for the specific release tags being created.
        """
        from ..utils.shell import exit_fatal

        # Check local git tags (direct ref lookup — O(1) each)
        repo = self.ctx.repo
        conflicts: list[str] = []
        for name, pkg in changed.items():
            for tag in (
                f"{name}/v{pkg.release_version}",
                f"{name}/v{pkg.next_version}-base",
            ):
                if repo.references.get(f"refs/tags/{tag}") is not None:
                    conflicts.append(tag)

        # Release conflicts: if the release tag exists locally,
        # a GitHub release almost certainly exists too (finalize pushes both).
        # No need for remote API calls — local refs are the source of truth.
        for name, pkg in changed.items():
            tag = f"{name}/v{pkg.release_version}"
            if tag not in conflicts:
                if repo.references.get(f"refs/tags/{tag}") is not None:
                    conflicts.append(tag)

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
