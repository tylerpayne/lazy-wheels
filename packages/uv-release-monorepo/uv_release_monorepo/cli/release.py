"""The ``uvr release`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..shared.models import ReleasePlan
from ..shared.utils.cli import __version__
from ..shared.utils.cli import fatal, read_matrix, resolve_plan_json

# Executor pipeline phases — the order ReleaseExecutor.run() executes them.
# These are skip-condition names (what appears in plan.skip) and YAML job keys.
_PIPELINE = ("uvr-build", "uvr-release", "uvr-bump")


def _compute_skipped(args: argparse.Namespace) -> set[str]:
    """Merge --skip and --skip-to into a single set of job names to skip."""
    skipped: set[str] = set(args.skip or [])

    skip_to = getattr(args, "skip_to", None)
    if skip_to:
        if skip_to not in _PIPELINE:
            fatal(f"--skip-to requires a pipeline phase: {', '.join(_PIPELINE)}")
        idx = _PIPELINE.index(skip_to)
        skipped |= set(_PIPELINE[:idx])

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
        return []
    try:
        from ..shared.utils.yaml import load_yaml

        doc = load_yaml(workflow)
        return list(doc.get("jobs", {}).keys())
    except Exception:
        return []


def _print_packages(plan: ReleasePlan) -> None:
    """Print the packages table."""
    from ..shared.utils.cli import diff_stat

    _section("Packages")
    all_names = sorted({*plan.changed, *plan.unchanged})
    if not all_names:
        return

    # Build rows: (status, name, current, will_release, previous, changes, commits)
    rows: list[tuple[str, ...]] = []
    for name in all_names:
        if name in plan.changed:
            pkg = plan.changed[name]
            baseline = f"{name}/v{pkg.current_version}-base"
            changes, commits = diff_stat(baseline, pkg.path)
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
                )
            )

    headers = (
        "STATUS",
        "PACKAGE",
        "CURRENT",
        "WILL RELEASE",
        "PREVIOUS",
        "CHANGES",
        "COMMITS",
    )
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def _row(cols: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cols, widths))

    print(f"  {_row(headers)}")
    for row in rows:
        print(f"  {_row(row)}")


def _print_plan(
    plan: ReleasePlan,
    skipped: set[str],
) -> None:
    """Print a human-readable summary of the release plan."""

    _print_packages(plan)

    # -- Pipeline (all jobs from release.yml) --
    _section("Pipeline")
    _sw = 6  # width of "STATUS"
    _D = " " * 14  # detail indent under phase
    print(f"  {'STATUS'.ljust(_sw)}  JOB")

    workflow_jobs = _load_workflow_jobs()
    # Ensure core jobs appear even if workflow can't be loaded
    if not workflow_jobs:
        workflow_jobs = ["uvr-validate", "uvr-build", "uvr-release", "uvr-bump"]

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

    where = getattr(args, "where", "ci")

    # --plan: execute a pre-computed plan locally
    raw_plan = getattr(args, "plan", None)
    if raw_plan:
        from ..shared.hooks import load_hook

        plan_json = resolve_plan_json(raw_plan)
        plan = ReleasePlan.model_validate_json(plan_json)
        hook = load_hook(Path.cwd())
        _cli.ReleaseExecutor(plan, hook).run()
        return

    # For CI mode, ensure clean worktree and workflow exists
    root = Path.cwd()
    json_only = getattr(args, "json", False)
    allow_dirty = getattr(args, "allow_dirty", False)
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

        workflow_path = root / args.workflow_dir / "release.yml"
        if not workflow_path.exists():
            fatal("No release workflow found. Run `uvr workflow init` first.")

    # Compute and validate skip/reuse
    skipped = _compute_skipped(args)
    reuse_run: str | None = getattr(args, "reuse_run", None)
    reuse_release: bool = getattr(args, "reuse_release", False)
    _validate_skip_reuse(skipped, reuse_run, reuse_release)

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
    from ..shared.utils.versions import detect_release_type

    # Steps: discover + resolve baselines + detect changes + compute versions + generate notes
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()  # suppress discovery print_step output
    progress = Progress(total_steps=5)
    try:
        ctx = build_context(progress=progress)

        dry_run = getattr(args, "dry_run", False) or json_only

        # Check for version conflicts (dev version of already-released version)
        from ..shared.utils.versions import find_version_conflicts

        version_conflicts = find_version_conflicts(ctx.packages, ctx.repo)
        if version_conflicts and not dry_run:
            lines = "\n".join(
                f"  {c.warning()}\n    Fix: {c.hint()}" for c in version_conflicts
            )
            fatal(f"Version conflicts detected:\n{lines}")

        # Apply --bump if provided (bump all packages before planning)
        bump_type = getattr(args, "bump", None)
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

        # Auto-detect release type from versions, allow CLI override
        release_type = getattr(args, "release_type", None) or detect_release_type(
            ctx.packages
        )
        config = _cli.PlanConfig(
            rebuild_all=args.rebuild_all,
            matrix=package_runners,
            uvr_version=__version__,
            python_version=getattr(args, "python_version", "3.12"),
            ci_publish=(where == "ci"),
            release_type=release_type,
            dry_run=dry_run,
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
        if getattr(args, "json", False):
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
        local_prefix = compatible_prefixes.get(system, "")
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

    # Apply --release-notes overrides
    for pkg_name, notes_value in getattr(args, "release_notes", None) or []:
        if pkg_name not in plan.changed:
            fatal(f"--release-notes: package {pkg_name!r} is not in the release plan.")
        if notes_value.startswith("@"):
            from pathlib import Path as _Path

            notes_path = _Path(notes_value[1:])
            if not notes_path.exists():
                fatal(f"--release-notes: file not found: {notes_path}")
            notes_text = notes_path.read_text()
        else:
            notes_text = notes_value
        plan.changed[pkg_name].release_notes = notes_text

    # --json: print only plan JSON to stdout and exit
    if getattr(args, "json", False):
        print(plan.model_dump_json(indent=2))
        return

    # Dry run: print summary and exit
    if getattr(args, "dry_run", False):
        _print_plan(plan, skipped)
        return

    # Print human-readable summary
    _print_plan(plan, skipped)

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

    if not getattr(args, "yes", False):
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
        except json.JSONDecodeError:
            pass
