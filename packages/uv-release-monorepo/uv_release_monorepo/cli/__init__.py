"""CLI entry point for uv-release-monorepo."""

from __future__ import annotations

import argparse

from ..pipeline import build_plan, execute_plan
from ..workflow_steps import run_pipeline
from ._common import (
    TEMPLATES_DIR,
    _HOOK_ALIASES,
    _VALID_HOOKS,
    _WorkflowConfig,
    __version__,
    _discover_package_names,
    _discover_packages,
    _empty_hooks,
    _fatal,
    _print_dependencies,
    _print_matrix_status,
    _read_matrix,
)
from ._workflow_state import _get_workflow_state, _render_workflow, _step_to_yaml
from ._yaml import _MISSING, _yaml_delete, _yaml_get, _yaml_set
from .hooks import (
    _hooks_apply,
    _hooks_interactive,
    _hooks_show,
    _parse_kv_pairs,
    _step_kwargs_from_args,
    cmd_hooks,
)
from .init import cmd_init
from .install import _find_latest_release_tag, _parse_install_spec, cmd_install
from .release import cmd_release
from .run import cmd_run
from .runners import cmd_runners
from .status import cmd_status
from .workflow import cmd_workflow

__all__ = [
    "TEMPLATES_DIR",
    "_HOOK_ALIASES",
    "_MISSING",
    "_VALID_HOOKS",
    "_WorkflowConfig",
    "__version__",
    "_discover_package_names",
    "_discover_packages",
    "_empty_hooks",
    "_fatal",
    "_find_latest_release_tag",
    "_get_workflow_state",
    "_hooks_apply",
    "_hooks_interactive",
    "_hooks_show",
    "_parse_install_spec",
    "_parse_kv_pairs",
    "_print_dependencies",
    "_print_matrix_status",
    "_read_matrix",
    "_render_workflow",
    "_step_kwargs_from_args",
    "_step_to_yaml",
    "_yaml_delete",
    "_yaml_get",
    "_yaml_set",
    "build_plan",
    "cli",
    "cmd_hooks",
    "cmd_init",
    "cmd_install",
    "cmd_release",
    "cmd_run",
    "cmd_runners",
    "cmd_status",
    "cmd_workflow",
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

    # hooks subcommand — uvr hooks PHASE [--add|--insert|--set|--remove|--clear]
    hooks_parser = subparsers.add_parser(
        "hooks",
        help="Manage CI hook steps in the release workflow.",
    )
    hooks_parser.add_argument(
        "hook_point",
        choices=["pre-build", "post-build", "pre-release", "post-release"],
        help="Hook phase.",
    )
    hooks_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing the workflow file. (default: %(default)s)",
    )
    _hooks_mut = hooks_parser.add_mutually_exclusive_group()
    _hooks_mut.add_argument(
        "--add",
        action="store_true",
        dest="do_add",
        help="Append a step (upsert if --id matches).",
    )
    _hooks_mut.add_argument(
        "--insert",
        action="store_true",
        dest="do_insert",
        help="Insert a step at --at position (1-indexed).",
    )
    _hooks_mut.add_argument(
        "--set",
        action="store_true",
        dest="do_set",
        help="Update the step at --at position (1-indexed).",
    )
    _hooks_mut.add_argument(
        "--remove",
        action="store_true",
        dest="do_remove",
        help="Remove the step at --at position (1-indexed).",
    )
    _hooks_mut.add_argument(
        "--clear",
        action="store_true",
        dest="do_clear",
        help="Remove all steps.",
    )
    hooks_parser.add_argument(
        "--at",
        type=int,
        dest="position",
        metavar="INDEX",
        help="Position (1-indexed) for --insert, --set, --remove.",
    )
    # Step fields
    hooks_parser.add_argument("--name", help="Step display name.")
    hooks_parser.add_argument("--run", help="Shell command to run.")
    hooks_parser.add_argument(
        "--uses", help="Action to use (e.g. actions/checkout@v4)."
    )
    hooks_parser.add_argument(
        "--with",
        dest="step_with",
        action="append",
        metavar="KEY=VALUE",
        help="Action input (repeatable).",
    )
    hooks_parser.add_argument(
        "--env",
        dest="step_env",
        action="append",
        metavar="KEY=VALUE",
        help="Environment variable (repeatable).",
    )
    hooks_parser.add_argument("--if", dest="step_if", help="Conditional expression.")
    hooks_parser.add_argument("--id", help="Unique id for upsert semantics.")
    hooks_parser.set_defaults(func=cmd_hooks)

    # workflow subcommand — uvr workflow PATH [VALUE]
    workflow_parser = subparsers.add_parser(
        "workflow",
        help="Get or set workflow-level YAML values.",
        description=(
            "Read or write any key in the release workflow YAML.\n\n"
            "Examples:\n"
            "  uvr workflow permissions                        # show permissions\n"
            "  uvr workflow permissions id-token write         # set a permission\n"
            "  uvr workflow permissions --clear                # reset permissions\n"
            "  uvr workflow jobs post-release environment pypi # set job key\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    workflow_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory containing the workflow file. (default: %(default)s)",
    )
    _wf_mut = workflow_parser.add_mutually_exclusive_group()
    _wf_mut.add_argument(
        "--set",
        dest="set_value",
        metavar="VALUE",
        help="Set the value at the given path.",
    )
    _wf_mut.add_argument(
        "--add",
        dest="add_value",
        metavar="VALUE",
        help="Append a value to the list at the given path.",
    )
    _wf_mut.add_argument(
        "--insert",
        dest="insert_value",
        metavar="VALUE",
        help="Insert a value into the list at the given path (requires --at).",
    )
    _wf_mut.add_argument(
        "--remove",
        dest="remove_value",
        metavar="VALUE",
        help="Remove a value from the list at the given path.",
    )
    _wf_mut.add_argument(
        "--clear",
        action="store_true",
        help="Delete the key at the given path.",
    )
    workflow_parser.add_argument(
        "--at",
        dest="insert_index",
        type=int,
        metavar="INDEX",
        help="Position for --insert (0-indexed).",
    )
    workflow_parser.add_argument(
        "path",
        nargs="*",
        metavar="KEY",
        help="Path into the YAML. E.g. 'permissions id-token'.",
    )
    workflow_parser.set_defaults(func=cmd_workflow)

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
