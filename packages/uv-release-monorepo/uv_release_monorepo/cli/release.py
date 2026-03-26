"""The ``uvr release`` command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..graph import topo_layers
from ..models import JOB_ORDER, ReleasePlan, ReleaseWorkflow, _NOOP_STEPS
from ._common import __version__, _fatal, _read_matrix
from ._yaml import _load_yaml


def _compute_skipped(args: argparse.Namespace) -> set[str]:
    """Merge --skip and --skip-to into a single set of job names to skip."""
    skipped: set[str] = set(args.skip or [])
    if args.skip_to:
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
    pin_changes: list[tuple[str, list[tuple[str, str]]]],
) -> None:
    """Print a human-readable summary of the release plan."""
    _HOOK_PHASES = {"pre-build", "post-build", "pre-release", "post-release"}

    # -- Packages --
    _section("Packages")
    all_names = sorted({*plan.changed, *plan.unchanged})
    if all_names:
        w = max(len(n) for n in all_names)
        for name in all_names:
            if name in plan.changed:
                info = plan.changed[name]
                tag = plan.release_tags.get(name)
                from_ver = tag.split("/v")[-1] if tag else "(first release)"
                print(f"  changed    {name.ljust(w)}  {from_ver} -> {info.version}")
            else:
                tag = plan.release_tags.get(name)
                source = tag or "(no prior release)"
                print(f"  unchanged  {name.ljust(w)}  reuse from {source}")

    # -- Dependency pins --
    if pin_changes:
        _section("Dependency pins")
        for name, changes in pin_changes:
            print(f"  {name}")
            for old, new in changes:
                print(f"    {old} -> {new}")

    # -- Pipeline (job-by-job with details inline) --
    _section("Pipeline")
    _D = "          "  # detail indent
    for job in JOB_ORDER:
        print()
        if job in skipped:
            reason = "no-op" if job in _HOOK_PHASES else "user --skip"
            print(f"  skip  {job}  ({reason})")
            continue

        print(f"  run   {job}")

        # Show build order inline under the build job
        if job == "build":
            if plan.reuse_run_id:
                print(f"{_D}artifacts from run {plan.reuse_run_id}")
            elif plan.matrix:
                layers = topo_layers(plan.changed)
                max_layer = max(layers.values()) if layers else 0
                by_runner: dict[str, list] = {}
                for me in plan.matrix:
                    by_runner.setdefault(me.runner, []).append(me)
                for runner, runner_entries in sorted(by_runner.items()):
                    print(f"{_D}{runner}")
                    for layer in range(max_layer + 1):
                        pkgs = [
                            e
                            for e in runner_entries
                            if layers.get(e.package, 0) == layer
                        ]
                        if not pkgs:
                            continue
                        if max_layer > 0:
                            print(f"{_D}  layer {layer}")
                        for e in pkgs:
                            print(f"{_D}    {e.package} ({e.version})")

        # Show publish entries inline under publish
        if job == "publish" and plan.publish_matrix:
            for entry in plan.publish_matrix:
                print(f"{_D}{entry.package}  {entry.version}  -> {entry.tag}")

        # Show version bumps inline under finalize
        if job == "finalize" and plan.bumps:
            for name, bump in sorted(plan.bumps.items()):
                print(f"{_D}{name}  -> {bump.new_version}.dev0")

    print()


def cmd_release(args: argparse.Namespace) -> None:
    """Generate a release plan and optionally dispatch the executor workflow."""
    # Late import to allow patching via ``uv_release_monorepo.cli.build_plan``.
    import uv_release_monorepo.cli as _cli

    root = Path.cwd()
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

    # Build the plan locally (suppress pipeline output — we print our own summary)
    import io
    import sys

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        plan, pin_changes = _cli.build_plan(
            rebuild_all=args.rebuild_all,
            matrix=package_runners,
            uvr_version=__version__,
            python_version=args.python_version,
        )
    finally:
        sys.stdout = old_stdout

    if not plan.changed:
        print("Nothing changed since last release. Use --rebuild-all to rebuild all.")
        return

    # Auto-skip hook jobs that only have the default no-op step
    _HOOK_PHASES = ["pre-build", "post-build", "pre-release", "post-release"]
    workflow_doc = _load_yaml(root / args.workflow_dir / "release.yml")
    model = ReleaseWorkflow.model_validate(workflow_doc)
    jobs_dict = model.model_dump(by_alias=True, exclude_none=True).get("jobs", {})
    for phase in _HOOK_PHASES:
        job = jobs_dict.get(phase, {})
        if job.get("steps") == _NOOP_STEPS:
            skipped.add(phase)

    # Set skip/reuse fields on the plan
    if skipped:
        plan.skip = sorted(skipped)
    if reuse_run:
        plan.reuse_run_id = reuse_run

    # Precompute the install spec for CI.
    # Don't pin to a .dev version -- it won't exist on PyPI.
    if ".dev" in plan.uvr_version:
        plan.uvr_version = ""
        plan.uvr_install = "uv-release-monorepo"
    else:
        plan.uvr_install = f"uv-release-monorepo=={plan.uvr_version}"

    # Print human-readable summary
    _print_plan(plan, skipped, pin_changes)

    # Prompt to write dep pins if needed
    if pin_changes:
        print()
        print("Packages need to pin new dependencies")
        print("--------------------------------------")
        print("The following commands will be run:")
        print()
        print("  1. Write updated pins to pyproject.toml files")
        print("  2. git add -A")
        print("  3. git commit -m 'chore: update dependency pins'")
        print("  4. git push")
        print()
        try:
            answer = input("Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer != "y":
            return
        from ..pipeline import write_dep_pins

        written = write_dep_pins(plan)
        for name, changes in written:
            for _old, new in changes:
                print(f"  {name}: {_old} -> {new}")
        print()
        print("Pin updates written. Commit and re-run:")
        print(
            "  git add -A && git commit -m 'chore: update dependency pins' && git push"
        )
        print("  uvr release")
        return

    # Optionally dump raw JSON
    if getattr(args, "json", False):
        print(json.dumps(plan.model_dump(), indent=2))
        print()

    # Build the dispatch command
    import subprocess
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

    # Prompt for confirmation before dispatching (skip with --yes)
    if not args.yes:
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

    # Wait for the run to be created and fetch its URL
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
