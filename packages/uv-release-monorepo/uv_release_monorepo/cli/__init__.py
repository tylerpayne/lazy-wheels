"""CLI entry point for uv-release-monorepo."""

from __future__ import annotations

import argparse

from ..shared.models import PlanConfig, ReleasePlan
from ..shared.plan import ReleasePlanner, build_plan
from ..shared.execute import ReleaseExecutor
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
from .init import cmd_init, cmd_validate
from .install import _find_latest_release_tag, _parse_install_spec, cmd_install
from .release import cmd_release
from .runners import cmd_runners

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
    "PlanConfig",
    "ReleaseExecutor",
    "ReleasePlanner",
    "build_plan",
    "cli",
    "cmd_init",
    "cmd_install",
    "cmd_release",
    "cmd_runners",
    "cmd_validate",
]


def cli() -> None:
    """Main CLI entry point."""
    _USAGE = """\
usage: uvr [-h] [--version] <command> ...

Lazy monorepo wheel builder — only rebuilds what changed.

Commands:
  release       Plan and execute a release (locally or via CI)
  status        Preview the release plan (alias for release --dry-run)
  runners       Manage per-package build runners
  install       Install a package from GitHub releases (org/repo/pkg)
  init          Scaffold the GitHub Actions workflow
  validate      Validate an existing release.yml

CI steps (used by the release workflow):
  build         Build packages for a runner
  finalize      Tag, bump versions, commit, and push

Low-level:
  pin-deps      Pin internal dependency versions in pyproject.toml

Options:
  -h, --help    Show this help message and exit
  --version     Show version number and exit

Run 'uvr <command> --help' for details on a specific command.
"""

    class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
        """Hide the auto-generated subparser list."""

        def _format_action(self, action: argparse.Action) -> str:
            if isinstance(action, argparse._SubParsersAction):
                return ""
            return super()._format_action(action)

    parser = argparse.ArgumentParser(
        prog="uvr",
        usage=argparse.SUPPRESS,
        formatter_class=_HelpFormatter,
        description=_USAGE,
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help=argparse.SUPPRESS)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help=argparse.SUPPRESS,
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, title=argparse.SUPPRESS, metavar=""
    )
    _H = argparse.SUPPRESS  # hide from parent help (our banner covers it)

    # -- User commands -------------------------------------------------

    # release (unified: replaces both old 'run' and 'release')
    release_parser = subparsers.add_parser(
        "release",
        help=_H,
        description=(
            "Plan and execute a release. By default, generates a plan and "
            "dispatches it to GitHub Actions. Use --where local to build and "
            "publish locally, or --dry-run to preview without changes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _mode = release_parser.add_argument_group("mode")
    _mode.add_argument(
        "--where",
        choices=["ci", "local"],
        default="ci",
        help="'ci' dispatches to GitHub Actions (default), "
        "'local' builds and publishes in this shell.",
    )
    _mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be released without making changes.",
    )
    _mode.add_argument(
        "--plan",
        default=None,
        metavar="JSON",
        help="Execute a pre-computed release plan locally.",
    )
    _build = release_parser.add_argument_group("build options")
    _build.add_argument(
        "--rebuild-all", action="store_true", help="Rebuild all packages."
    )
    _build.add_argument(
        "--python",
        default="3.12",
        metavar="VER",
        dest="python_version",
        help="Python version for CI builds (default: %(default)s).",
    )
    _rtype = release_parser.add_argument_group("release type (default: final)")
    _rtype_mut = _rtype.add_mutually_exclusive_group()
    _rtype_mut.add_argument(
        "--dev",
        action="store_const",
        const="dev",
        dest="release_type",
        help="Publish a dev release (as-is .devN version).",
    )
    _rtype_mut.add_argument(
        "--pre",
        choices=["a", "b", "rc"],
        dest="pre_kind",
        metavar="{a,b,rc}",
        help="Publish a pre-release (alpha, beta, or rc).",
    )
    _rtype_mut.add_argument(
        "--post",
        action="store_const",
        const="post",
        dest="release_type",
        help="Publish a post-release.",
    )
    _dispatch = release_parser.add_argument_group("dispatch (CI mode)")
    _dispatch.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt."
    )
    _dispatch.add_argument(
        "--skip",
        action="append",
        metavar="JOB",
        help="Skip a CI job (repeatable).",
        choices=["build", "publish", "finalize"],
    )
    _dispatch.add_argument(
        "--skip-to",
        metavar="JOB",
        help="Skip all CI jobs before JOB.",
        choices=["publish", "finalize"],
    )
    _dispatch.add_argument(
        "--reuse-run",
        metavar="RUN_ID",
        help="Reuse artifacts from a prior run.",
    )
    _dispatch.add_argument(
        "--reuse-release",
        action="store_true",
        help="Assume GitHub releases already exist.",
    )
    _local = release_parser.add_argument_group("local (--where local)")
    _local.add_argument(
        "--no-push",
        action="store_true",
        help="Skip git push after release.",
    )
    _out = release_parser.add_argument_group("output")
    _out.add_argument(
        "--json",
        action="store_true",
        help="Print only the plan JSON to stdout and exit.",
    )
    _out.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Workflow directory (default: %(default)s).",
    )
    release_parser.set_defaults(func=cmd_release)

    # status (alias for release --dry-run)
    def _cmd_status(a: argparse.Namespace) -> None:
        a.where = "ci"
        a.dry_run = True
        a.plan = None
        a.rebuild_all = False
        a.yes = False
        a.no_push = False
        a.python_version = "3.12"
        a.skip = None
        a.skip_to = None
        a.reuse_run = None
        a.reuse_release = False
        a.json = False
        cmd_release(a)

    status_parser = subparsers.add_parser("status", help=_H)
    status_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Workflow directory (default: %(default)s).",
    )
    status_parser.set_defaults(func=_cmd_status)

    # runners
    runners_parser = subparsers.add_parser("runners", help=_H)
    runners_parser.add_argument(
        "package",
        nargs="?",
        default=None,
        metavar="PKG",
        help="Package name (omit to show all).",
    )
    _rmut = runners_parser.add_mutually_exclusive_group()
    _rmut.add_argument("--add", dest="add_value", metavar="RUNNER")
    _rmut.add_argument("--remove", dest="remove_value", metavar="RUNNER")
    _rmut.add_argument("--clear", action="store_true")
    runners_parser.set_defaults(func=cmd_runners)

    # install
    install_parser = subparsers.add_parser("install", help=_H)
    install_parser.add_argument(
        "package",
        help="Install spec: ORG/REPO/PKG[@VERSION]",
    )
    install_parser.set_defaults(func=cmd_install)

    # init
    init_parser = subparsers.add_parser("init", help=_H)
    init_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory to write the workflow file (default: %(default)s).",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite release.yml without preserving existing hooks.",
    )
    init_parser.set_defaults(func=cmd_init)

    # validate
    validate_parser = subparsers.add_parser("validate", help=_H)
    validate_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Workflow directory (default: %(default)s).",
    )
    validate_parser.set_defaults(func=cmd_validate)

    # -- CI steps ------------------------------------------------------

    def _cmd_build(a: argparse.Namespace) -> None:
        plan = ReleasePlan.model_validate_json(a.plan)
        ReleaseExecutor(plan).build(runner=a.runner)

    build_parser = subparsers.add_parser("build", help=_H)
    build_parser.add_argument("--plan", required=True)
    build_parser.add_argument("--runner", required=True)
    build_parser.set_defaults(func=_cmd_build)

    def _cmd_finalize(a: argparse.Namespace) -> None:
        plan = ReleasePlan.model_validate_json(a.plan)
        ReleaseExecutor(plan).finalize()

    finalize_parser = subparsers.add_parser("finalize", help=_H)
    finalize_parser.add_argument("--plan", required=True)
    finalize_parser.set_defaults(func=_cmd_finalize)

    # -- Low-level -----------------------------------------------------

    def _cmd_pin_deps(a: argparse.Namespace) -> None:
        from pathlib import Path
        from ..shared.deps import pin_dependencies

        versions: dict[str, str] = {}
        for spec in a.specs:
            for sep in (">=", "=="):
                if sep in spec:
                    name, ver = spec.split(sep, 1)
                    versions[name.strip()] = ver.strip()
                    break
        pin_dependencies(Path(a.path), versions)

    pd_parser = subparsers.add_parser("pin-deps", help=_H)
    pd_parser.add_argument("--path", required=True)
    pd_parser.add_argument("specs", nargs="+")
    pd_parser.set_defaults(func=_cmd_pin_deps)

    args = parser.parse_args()
    args.func(args)
