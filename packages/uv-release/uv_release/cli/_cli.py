"""CLI entry point and argument parsing."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from pydantic import Field

from diny import inject, provider, singleton

from ..types.base import Frozen
from ..types.bump_kind import BumpKind
from ..dependencies.params.bump_params import NoPinDeps
from ..dependencies.params.bump_type import BumpType
from ..dependencies.params.version_mode import VersionMode, VersionOp
from ..dependencies.params.version_set import VersionSet
from ..dependencies.params.dev_release import DevRelease
from ..dependencies.params.package_selection import PackageSelection
from ..dependencies.params.no_commit import NoCommit
from ..dependencies.params.no_push import NoPush
from ..dependencies.params.release_target import ReleaseTarget
from ..dependencies.params.reuse_releases import ReuseReleases
from ..dependencies.params.reuse_run import ReuseRun
from ..dependencies.params.runner_filter import RunnerFilter
from ..dependencies.params.skip_jobs import SkipJobs
from ..dependencies.params.dry_run import DryRun
from ..dependencies.params.user_release_notes import UserReleaseNotes
from ..dependencies.params.configure_params import (
    ConfigureParams,
    ConfigurePublishParams,
    ConfigureRunnersParams,
)
from ..dependencies.params.download_params import DownloadParams
from ..dependencies.params.install_params import InstallParams
from ..dependencies.params.workflow_params import WorkflowParams
from ..dependencies.params.skill_params import SkillParams
from ..dependencies.release.release_guard import UserRecoverableError
from ..dependencies.shared.hooks import Hooks
from ..dependencies.shared.workflow_state import WorkflowState
from ..dependencies.shared.workspace_packages import WorkspacePackages


@singleton
class ParsedArgs(Frozen):
    """Raw parsed CLI arguments as a flat dict."""

    values: dict[str, Any] = Field(default_factory=dict)
    command: str = ""


@singleton
class Params(Frozen):
    """Common CLI params used across commands."""

    command: str = ""
    dry_run: bool = False
    yes: bool = False
    json_output: bool = False
    plan_json: str = ""


@provider(ParsedArgs)
def parse_args() -> ParsedArgs:
    parser = argparse.ArgumentParser(
        prog="uvr", description="Pure DI release pipeline."
    )
    sub = parser.add_subparsers(dest="command")

    # -- release --
    release_p = sub.add_parser("release", help="Plan and execute a release.")
    release_p.add_argument("--where", choices=["ci", "local"], default="ci")
    release_p.add_argument("--dry-run", action="store_true")
    release_p.add_argument("--all-packages", action="store_true")
    release_p.add_argument("--packages", nargs="*")
    release_p.add_argument("--not-packages", nargs="*", default=[])
    release_p.add_argument("--dev", action="store_true")
    release_p.add_argument("-y", "--yes", action="store_true")
    release_p.add_argument("--no-commit", action="store_true")
    release_p.add_argument("--no-push", action="store_true")
    release_p.add_argument("--reuse-run", default="")
    release_p.add_argument("--reuse-releases", action="store_true")
    release_p.add_argument("--runners", nargs="*", default=[])
    release_p.add_argument("--skip", nargs="*", default=[])
    release_p.add_argument("--skip-to", default="")
    release_p.add_argument(
        "--release-notes", nargs=2, action="append", metavar=("PACKAGE", "NOTES")
    )
    release_p.add_argument("--json", action="store_true", dest="json_output")
    release_p.add_argument("--plan", default="", dest="plan_json")

    # -- build --
    build_p = sub.add_parser("build", help="Build changed packages locally.")
    build_p.add_argument("--all-packages", action="store_true")
    build_p.add_argument("--packages", nargs="*")

    # -- version --
    ver_p = sub.add_parser("version", help="Read, set, or bump package versions.")
    ver_p.add_argument("--all-packages", action="store_true")
    ver_p.add_argument("--packages", nargs="*")
    ver_p.add_argument("--not-packages", nargs="*", default=[])
    ver_p.add_argument("--no-commit", action="store_true")
    ver_p.add_argument("--no-push", action="store_true")
    ver_p.add_argument("--no-pin", action="store_true")
    ver_p.add_argument("--force", action="store_true")
    ver_mode = ver_p.add_mutually_exclusive_group()
    ver_mode.add_argument("--set", default="", dest="version_set")
    ver_mode.add_argument(
        "--bump",
        nargs="?",
        const="auto",
        choices=["auto", "dev", "patch", "minor", "major", "post", "stable"],
        default="",
        dest="bump_kind",
    )

    # -- status --
    sub.add_parser("status", help="Show workspace status.")

    # -- configure (with publish/runners subcommands) --
    cfg_p = sub.add_parser("configure", help="Manage workspace configuration.")
    cfg_sub = cfg_p.add_subparsers(dest="cfg_subcommand")

    # configure (no subcommand) = workspace config
    cfg_p.add_argument("--latest", default=None)
    cfg_p.add_argument("--include", nargs="*", default=[])
    cfg_p.add_argument("--exclude", nargs="*", default=[])
    cfg_p.add_argument("--remove", nargs="*", default=[])
    cfg_p.add_argument("--clear", action="store_true")

    # configure publish
    cpub_p = cfg_sub.add_parser("publish", help="Manage publishing configuration.")
    cpub_p.add_argument("--index", default=None)
    cpub_p.add_argument("--environment", default=None)
    cpub_p.add_argument("--trusted-publishing", default=None)
    cpub_p.add_argument("--include", nargs="*", default=[])
    cpub_p.add_argument("--exclude", nargs="*", default=[])
    cpub_p.add_argument("--remove", nargs="*", default=[])
    cpub_p.add_argument("--clear", action="store_true")

    # configure runners
    crun_p = cfg_sub.add_parser("runners", help="Manage per-package CI runners.")
    crun_p.add_argument("--package", default="")
    crun_p.add_argument("--add", nargs="*", default=[])
    crun_p.add_argument("--remove", nargs="*", default=[])
    crun_p.add_argument("--clear", action="store_true")

    # -- clean --
    sub.add_parser("clean", help="Remove build caches.")

    # -- download --
    dl_p = sub.add_parser("download", help="Download wheels from a release.")
    dl_p.add_argument("package", nargs="?", default="")
    dl_p.add_argument("--release-tag", default="")
    dl_p.add_argument("--run-id", default="")
    dl_p.add_argument("--output", default="dist")
    dl_p.add_argument("--repo", default="")
    dl_p.add_argument("--all-platforms", action="store_true")

    # -- install --
    inst_p = sub.add_parser("install", help="Install packages from wheels.")
    inst_p.add_argument("packages", nargs="*", default=[])
    inst_p.add_argument("--dist", default="")
    inst_p.add_argument("--repo", default="")

    # -- workflow --
    wf_p = sub.add_parser("workflow", help="Manage release workflow.")
    wf_sub = wf_p.add_subparsers(dest="wf_subcommand")
    wf_val = wf_sub.add_parser("validate", help="Validate workflow against template.")
    wf_val.add_argument("--workflow-dir", default=".github/workflows")
    wf_val.add_argument("--diff", action="store_true", dest="show_diff")
    wf_inst = wf_sub.add_parser("install", help="Install or upgrade the workflow.")
    wf_inst.add_argument("--force", action="store_true")
    wf_inst.add_argument("--upgrade", action="store_true")
    wf_inst.add_argument("--workflow-dir", default=".github/workflows")
    wf_inst.add_argument("--editor", default="")
    # Hidden flag: print the bundled template to stdout and exit. Used by
    # --upgrade via `uvx --with uv-release=={prev} uvr workflow install
    # --print-template` to fetch the base for three-way merge.
    wf_inst.add_argument("--print-template", action="store_true")

    # -- skill --
    sk_p = sub.add_parser("skill", help="Manage Claude Code skills.")
    sk_sub = sk_p.add_subparsers(dest="sk_subcommand")
    sk_inst = sk_sub.add_parser("install", help="Install or upgrade skill files.")
    sk_inst.add_argument("--force", action="store_true")
    sk_inst.add_argument("--upgrade", action="store_true")
    sk_inst.add_argument("--editor", default="")
    # Hidden flag: print the bundled templates to stdout (concatenated with
    # path markers) and exit. Used by --upgrade via uvx to fetch base content.
    sk_inst.add_argument("--print-template", action="store_true")

    # -- jobs (CI-only, hidden) --
    jobs_p = sub.add_parser("jobs", help="Execute a job from a plan (CI).")
    jobs_p.add_argument("job_name", nargs="?", default="")

    ns = parser.parse_args()
    return ParsedArgs(values=vars(ns), command=ns.command or "")


# --- Providers: derive focused singletons from ParsedArgs ---


@provider(Params)
def provide_params(args: ParsedArgs) -> Params:
    return Params(
        command=args.command,
        dry_run=args.values.get("dry_run", False),
        yes=args.values.get("yes", False),
        json_output=args.values.get("json_output", False),
        plan_json=args.values.get("plan_json", "") or "",
    )


@provider(PackageSelection)
def provide_package_selection(args: ParsedArgs) -> PackageSelection:
    pkgs = args.values.get("packages") or []
    not_pkgs = args.values.get("not_packages") or []
    # --force on bump treats all packages as selected.
    force = args.values.get("force", False)
    return PackageSelection(
        all_packages=args.values.get("all_packages", False) or force,
        packages=frozenset(pkgs),
        exclude_packages=frozenset(not_pkgs),
    )


@provider(DevRelease)
def provide_dev_release(args: ParsedArgs) -> DevRelease:
    return DevRelease(value=args.values.get("dev", False))


@provider(ReleaseTarget)
def provide_release_target(args: ParsedArgs) -> ReleaseTarget:
    return ReleaseTarget(value=args.values.get("where", "local"))  # type: ignore[arg-type]


@provider(BumpType)
def provide_bump_type(args: ParsedArgs) -> BumpType:
    # --bump <axis> maps directly to a BumpKind.
    bump_kind = args.values.get("bump_kind", "") or ""
    if bump_kind:
        return BumpType(value=BumpKind(bump_kind))
    # --set has no bump kind, defaults to DEV for release pipeline usage.
    return BumpType(value=BumpKind.DEV)


@provider(VersionSet)
def provide_version_set(args: ParsedArgs) -> VersionSet:
    return VersionSet(value=args.values.get("version_set", "") or "")


@provider(VersionMode)
def provide_version_mode(args: ParsedArgs) -> VersionMode:
    if args.values.get("version_set", ""):
        return VersionMode(value=VersionOp.SET)
    if args.values.get("bump_kind", ""):
        return VersionMode(value=VersionOp.BUMP)
    return VersionMode(value=VersionOp.READ)


@provider(NoCommit)
def provide_no_commit(args: ParsedArgs) -> NoCommit:
    return NoCommit(value=args.values.get("no_commit", False))


@provider(NoPush)
def provide_no_push(args: ParsedArgs) -> NoPush:
    return NoPush(value=args.values.get("no_push", False))


@provider(NoPinDeps)
def provide_no_pin_deps(args: ParsedArgs) -> NoPinDeps:
    return NoPinDeps(value=args.values.get("no_pin", False))


@provider(ReuseRun)
def provide_reuse_run(args: ParsedArgs) -> ReuseRun:
    return ReuseRun(value=args.values.get("reuse_run", "") or "")


@provider(ReuseReleases)
def provide_reuse_releases(args: ParsedArgs) -> ReuseReleases:
    return ReuseReleases(value=args.values.get("reuse_releases", False))


@provider(RunnerFilter)
def provide_runner_filter(args: ParsedArgs) -> RunnerFilter:
    runners = args.values.get("runners") or []
    return RunnerFilter(value=frozenset(runners))


@provider(SkipJobs)
def provide_skip_jobs(args: ParsedArgs, workflow_state: WorkflowState) -> SkipJobs:
    skipped = set(args.values.get("skip") or [])
    skip_to = args.values.get("skip_to", "") or ""
    if skip_to and skip_to in workflow_state.job_names:
        idx = workflow_state.job_names.index(skip_to)
        skipped |= {j for j in workflow_state.job_names[:idx] if j != "validate"}
    return SkipJobs(value=frozenset(skipped))


@provider(DryRun)
def provide_dry_run(args: ParsedArgs) -> DryRun:
    return DryRun(value=args.values.get("dry_run", False))


@provider(UserReleaseNotes)
def provide_user_release_notes(args: ParsedArgs) -> UserReleaseNotes:
    """Parse --release-notes pairs. NOTES starting with @ reads from a file."""
    from pathlib import Path

    notes = args.values.get("release_notes")
    if not notes:
        return UserReleaseNotes()

    items: dict[str, str] = {}
    for pkg_name, notes_value in notes:
        if notes_value.startswith("@"):
            items[pkg_name] = Path(notes_value[1:]).read_text()
        else:
            items[pkg_name] = notes_value
    return UserReleaseNotes(items=items)


@provider(ConfigureParams)
def provide_configure_params(args: ParsedArgs) -> ConfigureParams:
    return ConfigureParams(
        latest=args.values.get("latest"),
        include_packages=args.values.get("include", []) or [],
        exclude_packages=args.values.get("exclude", []) or [],
        remove_packages=args.values.get("remove", []) or [],
        clear=args.values.get("clear", False),
    )


@provider(ConfigurePublishParams)
def provide_configure_publish_params(args: ParsedArgs) -> ConfigurePublishParams:
    return ConfigurePublishParams(
        index=args.values.get("index"),
        environment=args.values.get("environment"),
        trusted_publishing=args.values.get("trusted_publishing"),
        include_packages=args.values.get("include", []) or [],
        exclude_packages=args.values.get("exclude", []) or [],
        remove_packages=args.values.get("remove", []) or [],
        clear=args.values.get("clear", False),
    )


@provider(ConfigureRunnersParams)
def provide_configure_runners_params(args: ParsedArgs) -> ConfigureRunnersParams:
    return ConfigureRunnersParams(
        package=args.values.get("package", "") or "",
        add=args.values.get("add", []) or [],
        remove=args.values.get("remove", []) or [],
        clear=args.values.get("clear", False),
    )


@provider(DownloadParams)
def provide_download_params(args: ParsedArgs) -> DownloadParams:
    return DownloadParams(
        package=args.values.get("package", "") or "",
        release_tag=args.values.get("release_tag", "") or "",
        run_id=args.values.get("run_id", "") or "",
        output=args.values.get("output", "dist") or "dist",
        repo=args.values.get("repo", "") or "",
        all_platforms=args.values.get("all_platforms", False),
    )


@provider(InstallParams)
def provide_install_params(args: ParsedArgs) -> InstallParams:
    return InstallParams(
        packages=args.values.get("packages", []) or [],
        dist=args.values.get("dist", "") or "",
        repo=args.values.get("repo", "") or "",
    )


@provider(WorkflowParams)
def provide_workflow_params(args: ParsedArgs) -> WorkflowParams:
    editor = args.values.get("editor", "") or ""
    if not editor:
        editor = os.environ.get("VISUAL", "") or os.environ.get("EDITOR", "") or ""
    return WorkflowParams(
        subcommand=args.values.get("wf_subcommand", "") or "",
        force=args.values.get("force", False),
        upgrade=args.values.get("upgrade", False),
        print_template=args.values.get("print_template", False),
        workflow_dir=args.values.get("workflow_dir", ".github/workflows")
        or ".github/workflows",
        editor=editor,
        show_diff=args.values.get("show_diff", False),
    )


@provider(SkillParams)
def provide_skill_params(args: ParsedArgs) -> SkillParams:
    editor = args.values.get("editor", "") or ""
    if not editor:
        editor = os.environ.get("VISUAL", "") or os.environ.get("EDITOR", "") or ""
    return SkillParams(
        force=args.values.get("force", False),
        upgrade=args.values.get("upgrade", False),
        print_template=args.values.get("print_template", False),
        editor=editor,
    )


@inject
def cli(params: Params, hooks: Hooks, workspace: WorkspacePackages) -> None:
    hooks.pre_plan(workspace.root, params.command)
    try:
        match params.command:
            case "release":
                from .release import cmd_release

                cmd_release()
            case "build":
                from .build import cmd_build

                cmd_build()
            case "version":
                from .version import cmd_version

                cmd_version()
            case "status":
                from .status import cmd_status

                cmd_status()
            case "configure":
                _dispatch_configure()
            case "clean":
                from .clean import cmd_clean

                cmd_clean()
            case "download":
                from .download import cmd_download

                cmd_download()
            case "install":
                from .install import cmd_install

                cmd_install()
            case "workflow":
                from .workflow import cmd_workflow

                cmd_workflow()
            case "skill":
                from .skill_upgrade import cmd_skill_upgrade

                cmd_skill_upgrade()
            case "jobs":
                from .jobs import cmd_jobs

                cmd_jobs()
            case _:
                sys.exit(1)
    except UserRecoverableError as exc:
        if params.dry_run:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"\n{exc}")
        print("\nThe following commands will fix this:\n")
        for cmd in exc.fix_job.commands:
            print(f"  {cmd.label}")
        if not params.yes:
            print()
            try:
                answer = input("Apply fix? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                sys.exit(1)
            if answer != "y":
                sys.exit(1)
        from ..execute import execute_job

        execute_job(exc.fix_job, hooks)
        os.execvp(sys.argv[0], sys.argv)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


@inject
def _dispatch_configure(args: ParsedArgs) -> None:
    """Route configure to the right subcommand (or default to workspace config)."""
    cfg_sub = args.values.get("cfg_subcommand", "") or ""
    match cfg_sub:
        case "publish":
            from .configure_publish import cmd_configure_publish

            cmd_configure_publish()
        case "runners":
            from .configure_runners import cmd_configure_runners

            cmd_configure_runners()
        case _:
            from .configure import cmd_configure

            cmd_configure()
