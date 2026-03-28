"""The ``uvr release`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..shared.models import JOB_ORDER, ReleasePlan
from ._common import __version__, _fatal, _read_matrix, _resolve_plan_json


def _compute_skipped(args: argparse.Namespace) -> set[str]:
    """Merge --skip and --skip-to into a single set of job names to skip."""
    skipped: set[str] = set(args.skip or [])
    if getattr(args, "skip_to", None):
        idx = JOB_ORDER.index(args.skip_to)
        skipped |= set(JOB_ORDER[:idx])
    return skipped


def _validate_skip_reuse(
    skipped: set[str],
    reuse_run: str | None,
    reuse_release: bool,
) -> None:
    """Validate skip/reuse flag combinations."""
    build_skipped = "build" in skipped
    has_reuse = reuse_run is not None or reuse_release

    if build_skipped and not has_reuse:
        _fatal(
            "Build is being skipped but no artifact source specified.\n"
            "  Add --reuse-run RUN_ID or --reuse-release."
        )
    if has_reuse and not build_skipped:
        _fatal(
            "--reuse-run / --reuse-release requires build to be skipped.\n"
            "  Add --skip build or --skip-to <job-after-build>."
        )
    if reuse_run and reuse_release:
        _fatal("--reuse-run and --reuse-release are mutually exclusive.")


def _section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def _print_plan(
    plan: ReleasePlan,
    skipped: set[str],
) -> None:
    """Print a human-readable summary of the release plan."""

    # -- Packages --
    _section("Packages")
    all_names = sorted({*plan.changed, *plan.unchanged})
    if all_names:
        sw = len("unchanged")  # status column width
        nw = max(len(n) for n in all_names)
        # Column 3: current pyproject version, Column 4: release/reuse version
        cur_strs: dict[str, str] = {}
        rel_strs: dict[str, str] = {}
        for name in all_names:
            if name in plan.changed:
                cur_strs[name] = plan.current_versions.get(
                    name, plan.changed[name].version
                )
                rel_strs[name] = plan.changed[name].version
            else:
                cur_strs[name] = plan.unchanged[name].version
                rel_strs[name] = "—"
        cw = max(len(v) for v in cur_strs.values())

        # Header
        print(
            f"  {'STATUS'.ljust(sw)}  {'PACKAGE'.ljust(nw)}  "
            f"{'CURRENT'.ljust(cw)}  WILL RELEASE"
        )
        for name in all_names:
            status = "changed" if name in plan.changed else "unchanged"
            print(
                f"  {status.ljust(sw)}  {name.ljust(nw)}  "
                f"{cur_strs[name].ljust(cw)}  {rel_strs[name]}"
            )

    # -- Pipeline (job-by-job with details inline) --
    _section("Pipeline")
    _sw = 6  # width of "STATUS"
    _D = " " * 14  # detail indent under job
    print(f"  {'STATUS'.ljust(_sw)}  JOB")
    for job in JOB_ORDER:
        if job in skipped:
            print(f"  {'skip'.ljust(_sw)}  {job}  (--skip)")
            continue

        print(f"  {'run'.ljust(_sw)}  {job}")

        if job == "build":
            if plan.reuse_run_id:
                print(f"{_D}artifacts from run {plan.reuse_run_id}")
            elif plan.build_commands:
                # Collect assigned packages per runner for marking transitive deps
                assigned_by_runner: dict[tuple[str, ...], set[str]] = {}
                for me in plan.matrix:
                    assigned_by_runner.setdefault(tuple(me.runner), set()).add(
                        me.package
                    )

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
                            cur = plan.current_versions.get(pkg, "")
                            ver = (
                                plan.changed[pkg].version if pkg in plan.changed else ""
                            )
                            dep_marker = "" if pkg in assigned else " (dep)"
                            if cur and ver and cur != ver:
                                print(
                                    f"{_D}    {pkg.ljust(bw)}  "
                                    f"{cur} -> {ver}{dep_marker}"
                                )
                            else:
                                print(f"{_D}    {pkg.ljust(bw)}  {ver}{dep_marker}")

        if job == "publish" and plan.publish_matrix:
            for entry in plan.publish_matrix:
                print(f"{_D}{entry.tag}")

        if job == "finalize" and plan.bumps:
            fw = max(len(n) for n in plan.bumps)
            for name, bump in sorted(plan.bumps.items()):
                print(f"{_D}{name.ljust(fw)}  -> {bump.new_version}")

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

        plan_json = _resolve_plan_json(raw_plan)
        plan = ReleasePlan.model_validate_json(plan_json)
        hook = load_hook(Path.cwd())
        _cli.ReleaseExecutor(plan, hook).run()
        return

    # For CI mode, ensure clean worktree and workflow exists
    root = Path.cwd()
    json_only = getattr(args, "json", False)
    if where == "ci" and not json_only:
        result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        )
        if result.stdout.strip():
            _fatal(
                "Working tree is not clean. Commit or stash your changes first.\n"
                + result.stdout
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
            _fatal(
                "Local HEAD differs from remote. Pull or push first:\n"
                "  git pull --rebase && git push"
            )

        workflow_path = root / args.workflow_dir / "release.yml"
        if not workflow_path.exists():
            _fatal("No release workflow found. Run `uvr init` first.")

    # Compute and validate skip/reuse
    skipped = _compute_skipped(args)
    reuse_run: str | None = getattr(args, "reuse_run", None)
    reuse_release: bool = getattr(args, "reuse_release", False)
    _validate_skip_reuse(skipped, reuse_run, reuse_release)

    # Read stored matrix from pyproject.toml
    package_runners = _read_matrix(root)

    # Build the plan locally (suppress discovery output)
    import io
    import sys

    # Determine release type from flags
    pre_kind = getattr(args, "pre_kind", None) or ""
    release_type = getattr(args, "release_type", None) or (
        "pre" if pre_kind else "final"
    )

    # Load hook (if any) for pre_plan / post_plan
    from ..shared.hooks import load_hook

    hook = load_hook(root)

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        dry_run = getattr(args, "dry_run", False) or json_only
        config = _cli.PlanConfig(
            rebuild_all=args.rebuild_all,
            matrix=package_runners,
            uvr_version=__version__,
            python_version=getattr(args, "python_version", "3.12"),
            ci_publish=(where == "ci"),
            release_type=release_type,
            pre_kind=pre_kind,
            dry_run=dry_run,
        )
        if hook:
            config = hook.pre_plan(config)
        plan, _pin_changes = _cli.ReleasePlanner(config).plan()
    finally:
        sys.stdout = old_stdout

    if not plan.changed:
        if getattr(args, "json", False):
            print(plan.model_dump_json(indent=2))
        else:
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
            _fatal(
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
        _fatal("Failed to trigger workflow")

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
