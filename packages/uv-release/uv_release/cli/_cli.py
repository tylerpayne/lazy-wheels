"""Argparse setup and main entry point for the uvr CLI."""

from __future__ import annotations

import argparse

from .build import cmd_build
from .bump import cmd_bump
from .clean import cmd_clean
from .download import cmd_download
from .install import cmd_install
from .jobs import cmd_jobs
from .release import cmd_release
from .skill import cmd_skill_dispatch
from .status import cmd_status
from .workflow import cmd_init_dispatch


def build_parser() -> argparse.ArgumentParser:
    """Build the uvr argument parser."""
    parser = argparse.ArgumentParser(
        prog="uvr",
        description="Lazy monorepo wheel builder.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- status --------------------------------------------------------
    status_parser = subparsers.add_parser(
        "status", help="Show workspace package status"
    )
    status_parser.add_argument(
        "--rebuild-all", action="store_true", help="Show all packages as changed"
    )
    status_parser.add_argument(
        "--rebuild", nargs="+", metavar="PKG", help="Force specific packages changed"
    )
    status_parser.set_defaults(func=cmd_status)

    # -- build ---------------------------------------------------------
    build_parser = subparsers.add_parser("build", help="Build changed packages locally")
    build_parser.add_argument(
        "--rebuild-all", action="store_true", help="Build all packages"
    )
    build_parser.add_argument(
        "--packages", nargs="+", metavar="PKG", help="Only build specific packages"
    )
    build_parser.set_defaults(func=cmd_build)

    # -- release -------------------------------------------------------
    release_parser = subparsers.add_parser("release", help="Plan and execute a release")
    release_parser.add_argument(
        "--where",
        choices=["ci", "local"],
        default="ci",
        help="'ci' dispatches to GitHub Actions (default), 'local' runs here",
    )
    release_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without changes"
    )
    release_parser.add_argument(
        "--plan",
        default=None,
        metavar="JSON",
        help="Execute a pre-computed release plan",
    )
    release_parser.add_argument(
        "--rebuild-all", action="store_true", help="Rebuild all packages"
    )
    release_parser.add_argument(
        "--rebuild", nargs="+", metavar="PKG", help="Force rebuild specific packages"
    )
    release_parser.add_argument(
        "--dev",
        action="store_true",
        help="Publish .devN versions as-is",
    )
    release_parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation"
    )
    release_parser.add_argument(
        "--skip", action="append", metavar="JOB", help="Skip a CI job (repeatable)"
    )
    release_parser.add_argument(
        "--skip-to", metavar="JOB", help="Skip all jobs before JOB"
    )
    release_parser.add_argument(
        "--reuse-run", metavar="RUN_ID", help="Reuse artifacts from a prior CI run"
    )
    release_parser.add_argument(
        "--reuse-release",
        action="store_true",
        help="Assume GitHub releases already exist",
    )
    release_parser.add_argument("--no-push", action="store_true", help="Skip git push")
    release_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print plan JSON to stdout",
    )
    release_parser.add_argument(
        "--release-notes",
        nargs=2,
        action="append",
        metavar=("PKG", "NOTES"),
        help="Release notes for a package (use @file for file contents)",
    )
    release_parser.set_defaults(func=cmd_release)

    # -- bump ----------------------------------------------------------
    bump_parser = subparsers.add_parser("bump", help="Bump package versions")
    scope = bump_parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--all", action="store_true", dest="bump_all", help="Bump all packages"
    )
    scope.add_argument(
        "--packages", nargs="+", metavar="PKG", help="Bump specific packages"
    )
    bump_parser.add_argument(
        "--force", action="store_true", help="Skip changed-package guard"
    )
    bump_parser.add_argument(
        "--no-pin", action="store_true", help="Skip dependency pinning"
    )

    bump_type = bump_parser.add_mutually_exclusive_group(required=True)
    for bt in [
        "major",
        "minor",
        "patch",
        "alpha",
        "beta",
        "rc",
        "post",
        "dev",
        "stable",
    ]:
        bump_type.add_argument(
            f"--{bt}", action="store_const", const=bt, dest="bump_type"
        )
    bump_parser.set_defaults(func=cmd_bump)

    # -- workflow ------------------------------------------------------
    workflow_parser = subparsers.add_parser("workflow", help="Manage release workflow")
    workflow_sub = workflow_parser.add_subparsers(
        dest="workflow_command", required=True
    )

    wf_init = workflow_sub.add_parser("init", help="Scaffold or upgrade release.yml")
    wf_init.add_argument(
        "--workflow-dir", default=".github/workflows", help="Workflow directory"
    )
    wf_init.add_argument("--force", action="store_true", help="Overwrite existing")
    wf_init.add_argument(
        "--upgrade", action="store_true", help="Three-way merge upgrade"
    )
    wf_init.add_argument(
        "--base-only", action="store_true", help="Write merge bases only"
    )
    wf_init.add_argument(
        "--editor", default=None, help="Editor for conflict resolution"
    )
    wf_init.set_defaults(func=cmd_init_dispatch)

    from .workflow.validate import cmd_validate

    wf_validate = workflow_sub.add_parser("validate", help="Validate release.yml")
    wf_validate.add_argument(
        "--workflow-dir", default=".github/workflows", help="Workflow directory"
    )
    wf_validate.add_argument(
        "--diff", action="store_true", help="Show diff from template"
    )
    wf_validate.set_defaults(func=cmd_validate)

    from .workflow.runners import cmd_runners

    wf_runners = workflow_sub.add_parser("runners", help="Manage build runners")
    wf_runners.add_argument("package", nargs="?", default=None, help="Package name")
    wf_runners.add_argument(
        "--add",
        nargs="+",
        dest="add_runners",
        metavar="RUNNER",
        help="Add runner labels (comma-separated for multi-label)",
    )
    wf_runners.add_argument(
        "--remove",
        nargs="+",
        dest="remove_runners",
        metavar="RUNNER",
        help="Remove runner labels",
    )
    wf_runners.add_argument("--clear", action="store_true", help="Clear all runners")
    wf_runners.set_defaults(func=cmd_runners)

    from .workflow.publish import cmd_publish_config

    wf_publish = workflow_sub.add_parser("publish", help="Manage publish config")
    wf_publish.add_argument("--index", default=None, help="Default publish index")
    wf_publish.add_argument(
        "--environment", default=None, help="GitHub Actions environment"
    )
    wf_publish.add_argument(
        "--trusted-publishing",
        default=None,
        choices=["automatic", "always", "never"],
        help="Trusted publishing mode",
    )
    wf_publish.add_argument(
        "--include",
        nargs="+",
        dest="include_packages",
        metavar="PKG",
        help="Include packages for publishing",
    )
    wf_publish.add_argument(
        "--exclude",
        nargs="+",
        dest="exclude_packages",
        metavar="PKG",
        help="Exclude packages from publishing",
    )
    wf_publish.add_argument(
        "--remove",
        nargs="+",
        dest="remove_packages",
        metavar="PKG",
        help="Remove packages from include/exclude lists",
    )
    wf_publish.add_argument("--clear", action="store_true", help="Clear publish config")
    wf_publish.set_defaults(func=cmd_publish_config)

    from .workflow.config import cmd_config

    wf_config = workflow_sub.add_parser("config", help="Manage workspace config")
    wf_config.add_argument("--editor", default=None, help="Preferred editor")
    wf_config.add_argument(
        "--latest", default=None, help="Package with GitHub Latest badge"
    )
    wf_config.add_argument(
        "--include",
        nargs="+",
        dest="include_packages",
        metavar="PKG",
        help="Include packages",
    )
    wf_config.add_argument(
        "--exclude",
        nargs="+",
        dest="exclude_packages",
        metavar="PKG",
        help="Exclude packages",
    )
    wf_config.add_argument(
        "--remove",
        nargs="+",
        dest="remove_packages",
        metavar="PKG",
        help="Remove from include/exclude",
    )
    wf_config.add_argument(
        "--clear", action="store_true", help="Clear workspace config"
    )
    wf_config.set_defaults(func=cmd_config)

    # -- skill ---------------------------------------------------------
    skill_parser = subparsers.add_parser("skill", help="Manage Claude Code skills")
    skill_sub = skill_parser.add_subparsers(dest="skill_command", required=True)

    sk_init = skill_sub.add_parser("init", help="Copy or upgrade Claude skills")
    sk_init.add_argument("--force", action="store_true", help="Overwrite existing")
    sk_init.add_argument(
        "--upgrade", action="store_true", help="Three-way merge upgrade"
    )
    sk_init.add_argument(
        "--base-only", action="store_true", help="Write merge bases only"
    )
    sk_init.add_argument(
        "--editor", default=None, help="Editor for conflict resolution"
    )
    sk_init.set_defaults(func=cmd_skill_dispatch)

    # -- install -------------------------------------------------------
    install_parser = subparsers.add_parser(
        "install", help="Install from GitHub releases"
    )
    install_parser.add_argument(
        "packages", nargs="*", help="Package specs (pkg or pkg@version)"
    )
    install_parser.add_argument("--repo", default=None, help="GitHub repo (owner/name)")
    install_parser.add_argument(
        "--run-id", default=None, help="CI run ID for artifacts"
    )
    install_parser.add_argument("--dist", default=None, help="Local wheel directory")
    install_parser.set_defaults(func=cmd_install)

    # -- download ------------------------------------------------------
    download_parser = subparsers.add_parser(
        "download", help="Download wheels from GitHub"
    )
    download_parser.add_argument(
        "package", nargs="?", default=None, help="Package spec"
    )
    download_parser.add_argument(
        "--repo", default=None, help="GitHub repo (owner/name)"
    )
    download_parser.add_argument(
        "--release-tag", default=None, help="Release tag to download"
    )
    download_parser.add_argument("--run-id", default=None, help="CI run ID")
    download_parser.add_argument(
        "-o", "--output", default="dist", help="Output directory"
    )
    download_parser.add_argument(
        "--all-platforms", action="store_true", help="Download all platform wheels"
    )
    download_parser.set_defaults(func=cmd_download)

    # -- clean ---------------------------------------------------------
    clean_parser = subparsers.add_parser("clean", help="Remove uvr caches")
    clean_parser.set_defaults(func=cmd_clean)

    # -- jobs (hidden, used by CI) -------------------------------------
    jobs_parser = subparsers.add_parser("jobs")
    jobs_parser.add_argument("job_name", help="Job name to execute")
    jobs_parser.set_defaults(func=cmd_jobs)

    return parser


def cli() -> None:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
