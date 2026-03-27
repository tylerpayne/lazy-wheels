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
from .versions import (
    base_version,
    bump_dev,
    bump_patch,
    is_dev,
    make_dev,
    make_post,
    make_pre,
    next_post_number,
    next_pre_number,
    strip_dev,
    version_from_tag,
)
from .changes import detect_changes
from .discovery import discover_packages, find_release_tags, get_baseline_tags
from .publish import generate_release_notes
from .shell import git


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

        # Save current pyproject versions before transformation
        current_versions = {name: info.version for name, info in changed.items()}

        # Compute release versions based on release_type
        changed = self._compute_release_versions(changed, release_tags)

        # Compute published versions for internal dep pinning
        published_versions = self._published_versions(
            changed, changed_names, packages, release_tags
        )

        # Check dep pins without writing
        pin_changes = self._detect_pin_changes(
            changed_names, packages, published_versions
        )

        # Pre-compute version bumps (always bump to next .devN)
        bumps = self._compute_bumps(changed)

        # Expand matrix
        matrix_entries = self._expand_matrix(changed_names, changed)
        unique_runners = sorted(
            {tuple(e.runner) for e in matrix_entries}, key=lambda t: list(t)
        )
        runners_list: list[list[str]] = [list(t) for t in unique_runners]

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

        # Validate that no tags we'll create already exist
        self._check_tag_conflicts(changed, bumps)

        result_plan = ReleasePlan(
            uvr_version=self.config.uvr_version,
            python_version=self.config.python_version,
            rebuild_all=self.config.rebuild_all,
            release_type=self.config.release_type,
            changed=changed,
            unchanged=unchanged,
            current_versions=current_versions,
            release_tags=release_tags,
            matrix=matrix_entries,
            runners=runners_list,
            bumps=bumps,
            publish_matrix=publish_entries,
            ci_publish=self.config.ci_publish,
            build_commands=build_commands,
            publish_commands=publish_commands,
            finalize_commands=finalize_commands,
        )
        return result_plan, pin_changes

    def _compute_release_versions(
        self,
        changed: dict[str, PackageInfo],
        release_tags: dict[str, str | None],
    ) -> dict[str, PackageInfo]:
        """Compute the release version for each changed package.

        - final: strip .dev suffix → clean X.Y.Z
        - dev: keep as-is (publish the .devN version)
        - pre: rewrite to X.Y.Z{a,b,rc}N (auto-increment N from existing tags)
        - post: rewrite to X.Y.Z.postN (auto-increment N from existing tags)
        """
        rt = self.config.release_type
        result: dict[str, PackageInfo] = {}

        if rt == "dev":
            # Publish as-is — the .devN version in pyproject.toml is the release.
            # Error if any package doesn't have a .dev suffix.
            bad = {
                n: changed[n] for n in sorted(changed) if not is_dev(changed[n].version)
            }
            if bad:
                from .shell import fatal

                lines = "\n".join(
                    f"  uv version {make_dev(info.version)} --directory {info.path}"
                    for info in bad.values()
                )
                names = ", ".join(bad)
                fatal(
                    f"--dev release requires a .devN version in pyproject.toml, "
                    f"but these packages have clean versions: {names}\n"
                    f"Fix with:\n{lines}"
                )
            for name, info in changed.items():
                result[name] = info
        elif rt == "pre":
            all_tags = git("tag", "--list", check=False).splitlines()
            for name, info in changed.items():
                bv = base_version(info.version)
                n = next_pre_number(all_tags, name, self.config.pre_kind)
                version = make_pre(bv, self.config.pre_kind, n)
                result[name] = PackageInfo(
                    path=info.path, version=version, deps=info.deps
                )
        elif rt == "post":
            all_tags = git("tag", "--list", check=False).splitlines()
            for name, info in changed.items():
                bv = base_version(info.version)
                n = next_post_number(all_tags, name)
                version = make_post(bv, n)
                result[name] = PackageInfo(
                    path=info.path, version=version, deps=info.deps
                )
        else:
            # final: strip .dev suffix
            for name, info in changed.items():
                result[name] = PackageInfo(
                    path=info.path, version=strip_dev(info.version), deps=info.deps
                )

        return result

    def _compute_bumps(self, changed: dict[str, PackageInfo]) -> dict[str, BumpPlan]:
        """Compute the exact next pyproject.toml version after release.

        The returned new_version is written directly — no further transformation.

        - After final 1.0.1:      → 1.0.2.dev0
        - After dev 1.0.1.dev2:   → 1.0.1.dev3
        - After pre 1.0.1a0:      → 1.0.1a1.dev0  (dev toward next pre)
        - After post 1.0.0.post0: → 1.0.0.post0.dev0
        """
        rt = self.config.release_type
        bumps: dict[str, BumpPlan] = {}

        for name, info in changed.items():
            if rt == "dev":
                bumps[name] = BumpPlan(new_version=bump_dev(info.version))
            elif rt == "pre":
                # After 1.0.1a0 → 1.0.1a1.dev0 (increment pre number, add .dev0)
                kind = self.config.pre_kind
                # Extract current pre number and increment
                import re

                m = re.search(rf"{re.escape(kind)}(\d+)$", info.version)
                n = int(m.group(1)) + 1 if m else 1
                next_pre = make_pre(info.version, kind, n)
                bumps[name] = BumpPlan(new_version=make_dev(next_pre))
            elif rt == "post":
                # After 1.0.0.post0 → 1.0.0.post1.dev0 (dev toward next post)
                import re

                m = re.search(r"\.post(\d+)$", info.version)
                n = int(m.group(1)) + 1 if m else 1
                next_post = make_post(info.version, n)
                bumps[name] = BumpPlan(new_version=make_dev(next_post))
            else:
                bumps[name] = BumpPlan(new_version=make_dev(bump_patch(info.version)))

        return bumps

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
        import json as _json

        all_packages = {**changed, **unchanged}
        by_runner: dict[str, set[str]] = {}
        for entry in matrix_entries:
            key = _json.dumps(entry.runner)
            by_runner.setdefault(key, set()).add(entry.package)

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
            # new_version is the exact pyproject.toml version (already includes .dev)
            next_version = bump.new_version
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
                        next_version,
                    ],
                    label=f"Bump {name} to {next_version}",
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

    def _check_tag_conflicts(
        self,
        changed: dict[str, PackageInfo],
        bumps: dict[str, BumpPlan],
    ) -> None:
        """Verify that no tags or releases the plan will create already exist."""
        import json as _json

        from .shell import fatal, gh

        # Collect all tags the plan will create
        planned_tags: list[str] = []
        for name, info in changed.items():
            planned_tags.append(f"{name}/v{info.version}")
        for name, bump in bumps.items():
            planned_tags.append(f"{name}/v{bump.new_version}-base")

        # Check git tags
        existing_tags = set(git("tag", "--list", check=False).splitlines())
        tag_conflicts = [t for t in planned_tags if t in existing_tags]

        # Check GitHub releases (release tags created by publish action)
        existing_releases: set[str] = set()
        raw = gh("release", "list", "--json", "tagName", "--limit", "1000", check=False)
        if raw:
            try:
                for entry in _json.loads(raw):
                    existing_releases.add(entry["tagName"])
            except (_json.JSONDecodeError, KeyError):
                pass
        release_tags = [f"{n}/v{changed[n].version}" for n in changed]
        release_conflicts = [t for t in release_tags if t in existing_releases]

        conflicts = sorted(set(tag_conflicts + release_conflicts))
        if not conflicts:
            return

        lines = "\n".join(f"  {t}" for t in conflicts)

        # Compute what --post would produce for each conflicting release
        post_versions = []
        for t in conflicts:
            if t in existing_releases:
                ver = version_from_tag(t)
                post_ver = make_post(
                    ver, next_post_number(list(existing_releases), t.split("/v")[0])
                )
                post_versions.append(f"     {t.split('/v')[0]}: {post_ver}")

        post_hint = ""
        if post_versions:
            post_detail = "\n".join(post_versions)
            post_hint = f"  1. Use --post to publish a post-release:\n{post_detail}\n"
        else:
            post_hint = "  1. Use --post to publish a post-release\n"

        # Compute bump commands for each conflicting package
        bump_cmds = []
        for t in conflicts:
            if t in existing_releases:
                ver = version_from_tag(t)
                next_ver = make_dev(bump_patch(ver))
                pkg_name = t.split("/v")[0]
                pkg_path = (
                    changed[pkg_name].path
                    if pkg_name in changed
                    else f"packages/{pkg_name}"
                )
                bump_cmds.append(f"     uv version {next_ver} --directory {pkg_path}")

        bump_hint = ""
        if bump_cmds:
            bump_detail = "\n".join(bump_cmds)
            bump_hint = f"  2. Bump past the conflict:\n{bump_detail}\n"
        else:
            bump_hint = "  2. Bump to a new version: uv version <new-version> --directory <pkg>\n"

        fatal(
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
            runners = self.config.matrix.get(name, [["ubuntu-latest"]])
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
