"""The ``uvr release`` command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import Field

from ._args import CommandArgs
from ..shared.models import ReleasePlan
from ..shared.utils.cli import __version__
from ..shared.utils.cli import fatal, read_matrix, resolve_plan_json


class ReleaseArgs(CommandArgs):
    """Typed arguments for ``uvr release``."""

    where: str = "ci"
    dry_run: bool = False
    plan: str | None = None
    rebuild_all: bool = False
    allow_dirty: bool = False
    python_version: str = "3.12"
    release_type: str | None = None
    bump: str | None = None
    yes: bool = False
    skip: list[str] | None = None
    skip_to: str | None = None
    reuse_run: str | None = None
    reuse_release: bool = False
    workflow_dir: str = ".github/workflows"
    no_push: bool = False
    json_output: bool = Field(False, alias="json")
    release_notes: list[list[str]] | None = None
    pip_args: list[str] = []


_CORE_JOBS = {"uvr-validate", "uvr-build", "uvr-release", "uvr-bump"}
_FALLBACK_JOBS = ["uvr-validate", "uvr-build", "uvr-release", "uvr-bump"]


def _compute_skipped(parsed: ReleaseArgs, workflow_jobs: list[str]) -> set[str]:
    """Merge --skip and --skip-to into a single set of job names to skip."""
    skipped: set[str] = set(parsed.skip or [])

    skip_to = parsed.skip_to
    if skip_to:
        if skip_to not in workflow_jobs:
            fatal(
                f"Unknown job {skip_to!r} for --skip-to.\n"
                f"  Available jobs: {', '.join(workflow_jobs)}"
            )
        idx = workflow_jobs.index(skip_to)
        skipped |= {j for j in workflow_jobs[:idx] if j != "uvr-validate"}

    unknown = skipped - set(workflow_jobs)
    if unknown:
        fatal(
            f"Unknown job(s) for --skip: {', '.join(sorted(unknown))}.\n"
            f"  Available jobs: {', '.join(workflow_jobs)}"
        )

    if "uvr-validate" in skipped:
        fatal("uvr-validate cannot be skipped.")

    return skipped


def _validate_skip_reuse(
    skipped: set[str],
    reuse_run: str | None,
    reuse_release: bool,
) -> None:
    """Validate skip/reuse flag combinations."""
    build_skipped = "uvr-build" in skipped
    has_reuse = reuse_run is not None or reuse_release

    if build_skipped and not has_reuse:
        fatal(
            "Build is being skipped but no artifact source specified.\n"
            "  Add --reuse-run RUN_ID or --reuse-release."
        )
    if has_reuse and not build_skipped:
        fatal(
            "--reuse-run / --reuse-release requires build to be skipped.\n"
            "  Add --skip uvr-build or --skip-to <job-after-build>."
        )
    if reuse_run and reuse_release:
        fatal("--reuse-run and --reuse-release are mutually exclusive.")


def _section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def _load_workflow_jobs() -> list[str]:
    """Load job names from the worktree release.yml, preserving order."""
    from pathlib import Path

    workflow = Path.cwd() / ".github" / "workflows" / "release.yml"
    if not workflow.exists():
        return list(_FALLBACK_JOBS)
    try:
        from ..shared.utils.yaml import load_yaml

        doc = load_yaml(workflow)
        return list(doc.get("jobs", {}).keys()) or list(_FALLBACK_JOBS)
    except Exception as exc:
        print(f"WARNING: Could not load workflow: {exc}", file=sys.stderr)
        return list(_FALLBACK_JOBS)


def _print_packages(plan: ReleasePlan) -> None:
    """Print the packages table."""
    from ..shared.utils.cli import diff_stat

    _section("Packages")
    all_names = sorted({*plan.changed, *plan.unchanged})
    if not all_names:
        return

    rows: list[tuple[str, ...]] = []
    for name in all_names:
        if name in plan.changed:
            pkg = plan.changed[name]
            baseline = f"{name}/v{pkg.current_version}-base"
            changes, commits, diff_tag = diff_stat(
                baseline, pkg.path, fallback_tag=pkg.last_release_tag
            )
            prev = (
                pkg.last_release_tag.split("/v", 1)[1] if pkg.last_release_tag else "-"
            )
            rows.append(
                (
                    "changed",
                    name,
                    pkg.current_version,
                    pkg.release_version,
                    prev,
                    diff_tag,
                    changes,
                    commits,
                )
            )
        else:
            rows.append(
                (
                    "unchanged",
                    name,
                    plan.unchanged[name].version,
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                )
            )

    headers = (
        "STATUS",
        "PACKAGE",
        "CURRENT",
        "WILL RELEASE",
        "PREVIOUS",
        "DIFF FROM",
        "CHANGES",
        "COMMITS",
    )
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def _row(cols: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cols, widths))

    print(f"  {_row(headers)}")
    for row in rows:
        print(f"  {_row(row)}")


def _warn_missing_skip_guards(
    skipped: set[str],
    workflow_path: Path,
) -> None:
    """Warn if custom jobs being skipped don't check the plan's skip list."""
    from ..shared.utils.yaml import load_yaml

    custom_skipped = skipped - _CORE_JOBS
    if not custom_skipped:
        return

    try:
        doc = load_yaml(workflow_path)
    except Exception:
        return

    jobs = doc.get("jobs", {})
    for job_name in sorted(custom_skipped):
        job = jobs.get(job_name, {})
        if_cond = job.get("if", "")
        if f"contains(fromJSON(inputs.plan).skip, '{job_name}')" not in if_cond:
            print(
                f"WARNING: {job_name!r} is being skipped but its `if` condition "
                f"does not check the plan's skip list.\n"
                f"  Add: if: ${{{{ !contains(fromJSON(inputs.plan).skip, "
                f"'{job_name}') }}}}",
                file=sys.stderr,
            )


def _print_plan(
    plan: ReleasePlan,
    skipped: set[str],
    workflow_jobs: list[str],
) -> None:
    """Print a human-readable summary of the release plan."""

    _print_packages(plan)

    # -- Pipeline (all jobs from release.yml) --
    _section("Pipeline")
    _sw = 6  # width of "STATUS"
    _D = " " * 14  # detail indent under phase
    print(f"  {'STATUS'.ljust(_sw)}  JOB")

    for job in workflow_jobs:
        if job in skipped:
            print(f"  {'skip'.ljust(_sw)}  {job}  (--skip)")
        else:
            print(f"  {'run'.ljust(_sw)}  {job}")

        if job in skipped:
            continue

        # Build details
        if job == "uvr-build":
            if plan.reuse_run_id:
                print(f"{_D}artifacts from run {plan.reuse_run_id}")
            elif plan.build_commands:
                assigned_by_runner: dict[tuple[str, ...], set[str]] = {}
                for name, pkg in plan.changed.items():
                    for runner in pkg.runners:
                        assigned_by_runner.setdefault(tuple(runner), set()).add(name)

                all_build_pkgs: list[str] = []
                for stages in plan.build_commands.values():
                    for stage in stages:
                        all_build_pkgs.extend(stage.packages)
                bw = max(len(p) for p in all_build_pkgs) if all_build_pkgs else 0

                for runner_key in sorted(plan.build_commands):
                    assigned = assigned_by_runner.get(runner_key, set())
                    print(f"{_D}[{', '.join(runner_key)}]")
                    local_layer = 0
                    for stage in plan.build_commands[runner_key]:
                        pkgs = sorted(stage.packages)
                        if not pkgs:
                            continue
                        print(f"{_D}  layer {local_layer}")
                        local_layer += 1
                        for pkg in pkgs:
                            cpkg = plan.changed.get(pkg)
                            cur = cpkg.current_version if cpkg else ""
                            ver = cpkg.release_version if cpkg else ""
                            dep_marker = "" if pkg in assigned else " (dep)"
                            if cur and ver and cur != ver:
                                print(
                                    f"{_D}    {pkg.ljust(bw)}  "
                                    f"{cur} -> {ver}{dep_marker}"
                                )
                            else:
                                print(f"{_D}    {pkg.ljust(bw)}  {ver}{dep_marker}")

        # Release details
        elif job == "uvr-release" and plan.changed:
            for name, pkg in sorted(plan.changed.items()):
                print(f"{_D}{name}/v{pkg.release_version}")

        # Finalize details
        elif job == "uvr-bump":
            changed_with_bumps = {
                n: p for n, p in plan.changed.items() if p.next_version
            }
            if changed_with_bumps:
                fw = max(len(n) for n in changed_with_bumps)
                for name, pkg in sorted(changed_with_bumps.items()):
                    print(f"{_D}{name.ljust(fw)}  -> {pkg.next_version}")

    # -- Release Notes --
    notes_packages = {n: p for n, p in plan.changed.items() if p.release_notes.strip()}
    if notes_packages:
        _section("Release Notes")
        for name, pkg in sorted(notes_packages.items()):
            print(f"  {name}")
            for line in pkg.release_notes.strip().splitlines():
                print(f"    {line}")
            print()

    print()


def cmd_release(args: argparse.Namespace) -> None:
    """Plan and execute a release (locally or via CI)."""
    import uv_release_monorepo.cli as _cli

    import subprocess

    parsed = ReleaseArgs.from_namespace(args)
    where = parsed.where

    # --plan: execute a pre-computed plan locally
    if parsed.plan:
        from ..shared.hooks import load_hook

        plan_json = resolve_plan_json(parsed.plan)
        plan = ReleasePlan.model_validate_json(plan_json)
        hook = load_hook(Path.cwd())
        _cli.ReleaseExecutor(plan, hook).run()
        return

    # For CI mode, ensure clean worktree and workflow exists
    root = Path.cwd()
    json_only = parsed.json_output
    allow_dirty = parsed.allow_dirty
    workflow_path = root / parsed.workflow_dir / "release.yml"
    if where == "ci" and not json_only:
        result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        )
        if result.stdout.strip():
            if allow_dirty:
                import sys as _sys

                print(
                    f"WARNING: Working tree is not clean.\n{result.stdout}",
                    file=_sys.stderr,
                )
            else:
                fatal(
                    "Working tree is not clean. Commit or stash your changes first.\n"
                    "  Use --allow-dirty to proceed anyway.\n" + result.stdout
                )

        # Ensure local HEAD matches remote
        subprocess.run(["git", "fetch", "--quiet"], capture_output=True, check=False)
        local = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        remote = subprocess.run(
            ["git", "rev-parse", "@{u}"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if remote and local != remote:
            if allow_dirty:
                import sys as _sys

                print(
                    "WARNING: Local HEAD differs from remote.",
                    file=_sys.stderr,
                )
            else:
                fatal(
                    "Local HEAD differs from remote. Pull or push first:\n"
                    "  git pull --rebase && git push\n"
                    "  Use --allow-dirty to proceed anyway."
                )

        if not workflow_path.exists():
            fatal("No release workflow found. Run `uvr workflow init` first.")

    # Load workflow jobs for validation and display
    workflow_jobs = _load_workflow_jobs()

    # Compute and validate skip/reuse
    skipped = _compute_skipped(parsed, workflow_jobs)
    reuse_run = parsed.reuse_run
    reuse_release = parsed.reuse_release
    _validate_skip_reuse(skipped, reuse_run, reuse_release)

    # Warn if custom jobs being skipped lack the skip guard
    if workflow_path.exists():
        _warn_missing_skip_guards(skipped, workflow_path)

    # Read stored matrix from pyproject.toml
    package_runners = read_matrix(root)

    # Build the plan locally (suppress discovery output)
    import io
    import sys

    # Load hook (if any) for pre_plan / post_plan
    from ..shared.hooks import load_hook

    hook = load_hook(root)

    from ..shared.context import build_context
    from ..shared.utils.shell import Progress

    # Steps: discover + resolve baselines + detect changes + compute versions + generate notes
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()  # suppress discovery print_step output
    progress = Progress(total_steps=5)
    try:
        ctx = build_context(progress=progress)

        dry_run = parsed.dry_run or json_only

        # Check for version conflicts (dev version of already-released version)
        from ..shared.utils.versions import find_version_conflicts

        version_conflicts = find_version_conflicts(ctx.packages, ctx.repo)
        if version_conflicts:
            lines = "\n".join(
                f"  {c.warning()}\n    Fix: {c.hint()}" for c in version_conflicts
            )
            fatal(f"Version conflicts detected:\n{lines}")

        # Apply --bump if provided (bump all packages before planning)
        bump_type = parsed.bump
        if bump_type:
            from .bump import compute_bumped_version
            from ..shared.utils.versions import strip_dev

            if not dry_run:
                from ..shared.utils.dependencies import set_version

            for name, info in ctx.packages.items():
                new_version = compute_bumped_version(info.version, bump_type=bump_type)
                # Check if the bumped-to release version already exists
                release_ver = strip_dev(new_version)
                bump_tag = f"{name}/v{release_ver}"
                if ctx.repo.references.get(f"refs/tags/{bump_tag}") is not None:
                    fatal(
                        f"Cannot --bump {bump_type}: {name} {release_ver} was already "
                        f"released (tag: {bump_tag}). Bump further with uvr bump."
                    )
                if not dry_run:
                    set_version(Path(info.path) / "pyproject.toml", new_version)
                info.version = new_version

        # Parse --release-notes before planning so notes are baked into commands
        user_notes: dict[str, str] = {}
        for pkg_name, notes_value in parsed.release_notes or []:
            if notes_value.startswith("@"):
                notes_path = Path(notes_value[1:])
                if not notes_path.exists():
                    fatal(f"--release-notes: file not found: {notes_path}")
                user_notes[pkg_name] = notes_path.read_text()
            else:
                user_notes[pkg_name] = notes_value

        config = _cli.PlanConfig(
            rebuild_all=parsed.rebuild_all,
            matrix=package_runners,
            uvr_version=__version__,
            python_version=parsed.python_version,
            ci_publish=(where == "ci"),
            dev_release=parsed.release_type == "dev",
            dry_run=dry_run,
            release_notes=user_notes,
        )
        if hook:
            config = hook.pre_plan(config)

        plan = _cli.ReleasePlanner(config, ctx, progress=progress).plan()
    finally:
        sys.stdout = old_stdout

    if plan.changed:
        progress.complete("Generated release plan")
    progress.finish(release_count=len(plan.changed))

    if not plan.changed:
        if json_only:
            print(plan.model_dump_json(indent=2))
        else:
            _print_packages(plan)
            print()
            print(
                "Nothing changed since last release. Use --rebuild-all to rebuild all."
            )
        return

    # Local mode: warn if packages have platform-specific runners configured
    if where == "local" and package_runners:
        import platform

        system = platform.system().lower()
        compatible_prefixes = {
            "darwin": "macos",
            "linux": "ubuntu",
            "windows": "windows",
        }
        local_prefix = compatible_prefixes.get(system)
        if not local_prefix:
            fatal(f"Unsupported platform for local release: {system}")
        incompatible: list[str] = []
        for pkg, runners in package_runners.items():
            if pkg not in plan.changed:
                continue
            for labels in runners:
                if not any(label.startswith(local_prefix) for label in labels):
                    incompatible.append(f"  {pkg}: [{', '.join(labels)}]")
        if incompatible:
            lines = "\n".join(incompatible)
            fatal(
                f"--where local but these changed packages have runners for a "
                f"different platform ({system}):\n{lines}\n"
                f"Use 'uvr release' (CI mode) instead, or remove custom runners:\n"
                f"  uvr runners <pkg> --clear"
            )

    # Set skip/reuse fields on the plan
    if skipped:
        plan.skip = sorted(skipped)
    if reuse_run:
        plan.reuse_run_id = reuse_run

    # Run post-plan hook if configured
    if hook:
        plan = hook.post_plan(plan)

    # --json: print only plan JSON to stdout and exit
    if json_only:
        print(plan.model_dump_json(indent=2))
        return

    # Dry run: print summary and exit
    if parsed.dry_run:
        _print_plan(plan, skipped, workflow_jobs)
        return

    # Print human-readable summary
    _print_plan(plan, skipped, workflow_jobs)

    # Commit release versions and pinned deps (planner wrote them locally)
    subprocess.run(
        ["uv", "sync", "--all-groups", "--all-extras"],
        capture_output=True,
        check=True,
    )
    pyproject_paths = [
        f"{plan.changed[name].path}/pyproject.toml" for name in sorted(plan.changed)
    ]
    subprocess.run(["git", "add", "uv.lock", *pyproject_paths], check=True)
    # Check if there are staged changes to commit
    diff_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], capture_output=True
    )
    if diff_result.returncode != 0:
        version_summary = ", ".join(
            f"{name} {plan.changed[name].version}" for name in sorted(plan.changed)
        )
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"chore: set release versions\n\n{version_summary}",
            ],
            check=True,
        )
        if where == "ci":
            subprocess.run(["git", "push"], check=True)

    if where == "local":
        # Execute locally
        _cli.ReleaseExecutor(plan, hook).run()
        return

    # CI mode: dispatch to GitHub Actions
    # Precompute the install spec for CI
    if ".dev" in plan.uvr_version:
        plan.uvr_version = ""
        plan.uvr_install = "uv-release-monorepo"
    else:
        plan.uvr_install = f"uv-release-monorepo=={plan.uvr_version}"

    import time

    plan_json = plan.model_dump_json()
    ref_result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
    )
    ref = ref_result.stdout.strip() if ref_result.returncode == 0 else "main"
    cmd = [
        "gh",
        "workflow",
        "run",
        "release.yml",
        "--ref",
        ref,
        "-f",
        f"plan={plan_json}",
    ]

    if not parsed.yes:
        print()
        print("Dispatch release")
        print("----------------")
        print(
            f"  gh workflow run release.yml --ref {ref} -f plan=<{len(plan_json)} bytes>"
        )
        if plan.skip:
            print(f"  skip: {', '.join(plan.skip)}")
        print()
        try:
            answer = input("Run this command? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer != "y":
            return

    print(f"Dispatching release for: {', '.join(sorted(plan.changed))}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        fatal("Failed to trigger workflow")

    print("Waiting for workflow run...")
    time.sleep(2)

    result = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--workflow=release.yml",
            "--limit=1",
            "--json=url,status",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout:
        try:
            runs = json.loads(result.stdout)
            if runs:
                url = runs[0].get("url", "")
                status = runs[0].get("status", "")
                print(f"Status: {status}")
                print(f"Watch:  {url}")
        except json.JSONDecodeError as exc:
            print(f"WARNING: Could not parse run status: {exc}", file=sys.stderr)
