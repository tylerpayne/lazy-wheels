"""CLI entry point for uv-release-monorepo."""

from __future__ import annotations

import argparse

from ..pipeline import build_plan, execute_plan
from ..workflow_steps import run_pipeline
from ._common import (
    __version__,
    _discover_package_names,
    _discover_packages,
    _fatal,
    _print_dependencies,
    _print_matrix_status,
    _read_matrix,
)
from ._yaml import _MISSING, _yaml_delete, _yaml_get, _yaml_set
from .init import cmd_init
from .install import _find_latest_release_tag, _parse_install_spec, cmd_install
from .release import cmd_release
from .run import cmd_run
from .runners import cmd_runners
from .status import cmd_status

__all__ = [
    "_MISSING",
    "__version__",
    "_discover_package_names",
    "_discover_packages",
    "_fatal",
    "_find_latest_release_tag",
    "_parse_install_spec",
    "_print_dependencies",
    "_print_matrix_status",
    "_read_matrix",
    "_yaml_delete",
    "_yaml_get",
    "_yaml_set",
    "build_plan",
    "cli",
    "cmd_init",
    "cmd_install",
    "cmd_release",
    "cmd_run",
    "cmd_runners",
    "cmd_status",
    "execute_plan",
    "run_pipeline",
]


def cli() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="uvr",
        description="Lazy monorepo wheel builder \u2014 only rebuilds what changed.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init subcommand
    init_parser = subparsers.add_parser(
        "init", help="Scaffold the GitHub Actions workflow into your repo."
    )
    init_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory to write the workflow file. (default: %(default)s)",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite release.yml without preserving existing hooks.",
    )
    init_parser.set_defaults(func=cmd_init)

    # runners subcommand
    runners_parser = subparsers.add_parser(
        "runners", help="Manage per-package build runners."
    )
    runners_parser.add_argument(
        "package",
        nargs="?",
        default=None,
        metavar="PKG",
        help="Package name (omit to show all).",
    )
    _runners_mut = runners_parser.add_mutually_exclusive_group()
    _runners_mut.add_argument(
        "--add",
        dest="add_value",
        metavar="RUNNER",
        help="Add a runner for the package.",
    )
    _runners_mut.add_argument(
        "--remove",
        dest="remove_value",
        metavar="RUNNER",
        help="Remove a runner from the package.",
    )
    _runners_mut.add_argument(
        "--clear",
        action="store_true",
        help="Remove all runners for the package.",
    )
    runners_parser.set_defaults(func=cmd_runners)

    # run subcommand
    run_parser = subparsers.add_parser(
        "run", help="Run the release pipeline locally (usually called from CI)."
    )
    run_parser.add_argument(
        "--rebuild-all", action="store_true", help="Rebuild all packages."
    )
    run_parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip git push (useful when workflow handles push separately).",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be released without making any changes.",
    )
    run_parser.add_argument(
        "--plan",
        default=None,
        help="Execute a pre-computed release plan JSON instead of running discovery.",
    )
    run_parser.set_defaults(func=cmd_run)

    # release subcommand
    release_parser = subparsers.add_parser(
        "release",
        help="Generate a release plan locally and dispatch the executor workflow.",
    )
    release_parser.add_argument(
        "--rebuild-all", action="store_true", help="Rebuild all packages."
    )
    release_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt and dispatch immediately.",
    )
    release_parser.add_argument(
        "--python",
        default="3.12",
        metavar="VERSION",
        dest="python_version",
        help="Python version for CI builds. (default: %(default)s)",
    )
    release_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing the workflow file. (default: %(default)s)",
    )
    release_parser.add_argument(
        "--skip",
        action="append",
        choices=[
            "pre-build",
            "build",
            "post-build",
            "pre-release",
            "publish",
            "finalize",
            "post-release",
        ],
        metavar="JOB",
        help="Skip a job (repeatable). Valid: pre-build, build, post-build, pre-release, publish, finalize, post-release.",
    )
    release_parser.add_argument(
        "--skip-to",
        choices=[
            "build",
            "post-build",
            "pre-release",
            "publish",
            "finalize",
            "post-release",
        ],
        metavar="JOB",
        help="Skip all jobs before JOB.",
    )
    release_parser.add_argument(
        "--reuse-run",
        metavar="RUN_ID",
        help="Download build artifacts from a previous workflow run (requires build to be skipped).",
    )
    release_parser.add_argument(
        "--reuse-release",
        action="store_true",
        help="Assume GitHub releases already exist (requires build and publish to be skipped).",
    )
    release_parser.add_argument(
        "--json",
        action="store_true",
        help="Also print the raw plan JSON.",
    )
    release_parser.set_defaults(func=cmd_release)

    # status subcommand
    status_parser = subparsers.add_parser(
        "status", help="Show the current workflow configuration."
    )
    status_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing the workflow file. (default: %(default)s)",
    )
    status_parser.set_defaults(func=cmd_status)

    # install subcommand
    install_parser = subparsers.add_parser(
        "install",
        help="Install a workspace package and its internal deps from GitHub releases.",
    )
    install_parser.add_argument(
        "package",
        help="Package name, optionally pinned: PACKAGE[@VERSION]",
    )
    install_parser.set_defaults(func=cmd_install)

    args = parser.parse_args()
    args.func(args)
