"""The ``uvr release`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..shared.graph import topo_layers
from ..shared.models import JOB_ORDER, ReleasePlan
from ._common import __version__, _fatal, _read_matrix


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
            elif plan.matrix:
                layers = topo_layers(plan.changed)
                max_layer = max(layers.values()) if layers else 0
                import json as _json

                by_runner: dict[str, list] = {}
                for me in plan.matrix:
                    key = _json.dumps(me.runner)
                    by_runner.setdefault(key, []).append(me)
                all_build_pkgs = [e.package for e in plan.matrix]
                bw = max(len(p) for p in all_build_pkgs) if all_build_pkgs else 0
                for runner_key, runner_entries in sorted(by_runner.items()):
                    labels = _json.loads(runner_key)
                    print(f"{_D}[{', '.join(labels)}]")
                    local_layer = 0
                    for layer in range(max_layer + 1):
                        pkgs = [
                            e
                            for e in runner_entries
                            if layers.get(e.package, 0) == layer
                        ]
                        if not pkgs:
                            continue
                        if max_layer > 0:
                            print(f"{_D}  layer {local_layer}")
                        local_layer += 1
                        for e in pkgs:
                            cur = plan.current_versions.get(e.package, e.version)
                            if cur != e.version:
                                print(
                                    f"{_D}    {e.package.ljust(bw)}  "
                                    f"{cur} -> {e.version}"
                                )
                            else:
                                print(f"{_D}    {e.package.ljust(bw)}  {e.version}")

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
    if getattr(args, "plan", None):
        plan = ReleasePlan.model_validate_json(args.plan)
        _cli.ReleaseExecutor(plan).run()
        return

    # For CI mode, ensure clean worktree and workflow exists
    root = Path.cwd()
    if where == "ci":
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

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        plan, _pin_changes = _cli.ReleasePlanner(
            _cli.PlanConfig(
                rebuild_all=args.rebuild_all,
                matrix=package_runners,
                uvr_version=__version__,
                python_version=getattr(args, "python_version", "3.12"),
                ci_publish=(where == "ci"),
                release_type=release_type,
                pre_kind=pre_kind,
            )
        ).plan()
    finally:
        sys.stdout = old_stdout

    if not plan.changed:
        print("Nothing changed since last release. Use --rebuild-all to rebuild all.")
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

    # Dry run: print summary and exit
    if getattr(args, "dry_run", False):
        _print_plan(plan, skipped)
        return

    # Set skip/reuse fields on the plan
    if skipped:
        plan.skip = sorted(skipped)
    if reuse_run:
        plan.reuse_run_id = reuse_run

    # Print human-readable summary
    _print_plan(plan, skipped)

    # Optionally dump raw JSON
    if getattr(args, "json", False):
        print(json.dumps(plan.model_dump(), indent=2))
        print()

    if where == "local":
        # Execute locally
        _cli.ReleaseExecutor(plan).run()
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
    cmd = [
        "gh",
        "workflow",
        "run",
        "release.yml",
        "-f",
        f"plan={plan_json}",
    ]

    if not getattr(args, "yes", False):
        print()
        print("Dispatch release")
        print("----------------")
        print(f"  gh workflow run release.yml -f plan=<{len(plan_json)} bytes>")
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
