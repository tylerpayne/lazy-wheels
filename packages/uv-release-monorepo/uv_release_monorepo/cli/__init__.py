"""CLI entry point for uv-release-monorepo."""

from __future__ import annotations

import argparse

from ..shared.models import PlanConfig, ReleasePlan
from ..shared.planner import ReleasePlanner, build_plan
from ..shared.executor import ReleaseExecutor
from ._common import (
    __version__,
    _discover_package_names,
    _discover_packages,
    _fatal,
    _print_dependencies,
    _print_matrix_status,
    _read_matrix,
    _resolve_plan_json,
)
from ._yaml import _MISSING, _yaml_delete, _yaml_get, _yaml_set
from .init import cmd_init, cmd_upgrade, cmd_validate
from ._common import _parse_install_spec
from ..shared.utils.tags import (
    find_latest_remote_release_tag as _find_latest_release_tag,
)
from .install import cmd_install
from .bump import cmd_bump
from .release import cmd_release
from .runners import cmd_runners
from .skill import cmd_skill_init, cmd_skill_upgrade
from .wheels import cmd_wheels

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
    "cmd_bump",
    "PlanConfig",
    "ReleaseExecutor",
    "ReleasePlanner",
    "build_plan",
    "cli",
    "cmd_init",
    "cmd_install",
    "cmd_release",
    "cmd_runners",
    "cmd_upgrade",
    "cmd_validate",
    "cmd_wheels",
]


def cli() -> None:
    """Main CLI entry point."""
    _USAGE = """\
usage: uvr [-h] [--version] <command> ...

Lazy monorepo wheel builder — only rebuilds what changed.

Commands:
  release       Plan and execute a release (locally or via CI)
  bump          Bump package versions in the workspace
  status        Preview the release plan (alias for release --dry-run)
  runners       Manage per-package build runners
  install       Install a package from GitHub releases (org/repo/pkg)
  wheels        Download wheels from GitHub releases or CI artifacts
  init          Scaffold the GitHub Actions workflow
  validate      Validate an existing release.yml
  skill init    Copy Claude Code skills into your project

CI steps (used by the release workflow):
  validate-plan Validate and pretty-print the release plan
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
        "--allow-dirty",
        action="store_true",
        help="Proceed even if the working tree has uncommitted changes.",
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
        action="store_const",
        const="pre",
        dest="release_type",
        help="Publish the pre-release version as-is (requires pre suffix).",
    )
    _rtype_mut.add_argument(
        "--post",
        action="store_const",
        const="post",
        dest="release_type",
        help="Publish a post-release.",
    )
    _rtype_mut.add_argument(
        "--minor",
        action="store_const",
        const="minor",
        dest="release_type",
        help="Bump minor version and release (X.Y+1.0).",
    )
    _rtype_mut.add_argument(
        "--major",
        action="store_const",
        const="major",
        dest="release_type",
        help="Bump major version and release (X+1.0.0).",
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
    )
    _dispatch.add_argument(
        "--skip-to",
        metavar="JOB",
        help="Skip all CI jobs before JOB.",
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
    _out.add_argument(
        "--release-notes",
        nargs=2,
        action="append",
        metavar=("PKG", "NOTES"),
        help="Set release notes for a package. NOTES is inline text or @file.",
    )
    release_parser.set_defaults(func=cmd_release)

    # status (alias for release --dry-run)
    def _cmd_status(a: argparse.Namespace) -> None:
        a.where = "ci"
        a.dry_run = True
        a.plan = None
        a.rebuild_all = getattr(a, "rebuild_all", False)
        a.allow_dirty = getattr(a, "allow_dirty", False)
        a.yes = False
        a.no_push = False
        a.python_version = "3.12"
        a.skip = None
        a.skip_to = None
        a.reuse_run = None
        a.reuse_release = False
        a.json = False
        a.release_type = None
        cmd_release(a)

    status_parser = subparsers.add_parser("status", help=_H)
    status_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Workflow directory (default: %(default)s).",
    )
    status_parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Proceed even if the working tree has uncommitted changes.",
    )
    status_parser.add_argument(
        "--rebuild-all",
        action="store_true",
        help="Show plan as if all packages changed.",
    )
    status_parser.set_defaults(func=_cmd_status)

    # bump
    bump_parser = subparsers.add_parser(
        "bump",
        help=_H,
        description="Bump package versions in the workspace.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _bscope = bump_parser.add_argument_group("scope (required)")
    _bscope_mut = _bscope.add_mutually_exclusive_group(required=True)
    _bscope_mut.add_argument(
        "--all",
        action="store_true",
        dest="bump_all",
        help="Bump all workspace packages.",
    )
    _bscope_mut.add_argument(
        "--changed",
        action="store_true",
        help="Bump only packages with changes since last release.",
    )
    _bscope_mut.add_argument(
        "--package",
        action="append",
        dest="packages",
        metavar="PKG",
        help="Bump a specific package (repeatable).",
    )
    _btype = bump_parser.add_argument_group("bump type (required)")
    _btype_mut = _btype.add_mutually_exclusive_group(required=True)
    _btype_mut.add_argument(
        "--major",
        action="store_const",
        const="major",
        dest="bump_type",
        help="Bump major version: (X+1).0.0.dev0",
    )
    _btype_mut.add_argument(
        "--minor",
        action="store_const",
        const="minor",
        dest="bump_type",
        help="Bump minor version: X.(Y+1).0.dev0",
    )
    _btype_mut.add_argument(
        "--patch",
        action="store_const",
        const="patch",
        dest="bump_type",
        help="Bump patch version: X.Y.(Z+1).dev0",
    )
    _btype_mut.add_argument(
        "--alpha",
        action="store_const",
        const="alpha",
        dest="bump_type",
        help="Enter alpha pre-release cycle.",
    )
    _btype_mut.add_argument(
        "--beta",
        action="store_const",
        const="beta",
        dest="bump_type",
        help="Enter beta pre-release cycle.",
    )
    _btype_mut.add_argument(
        "--rc",
        action="store_const",
        const="rc",
        dest="bump_type",
        help="Enter release candidate cycle.",
    )
    _btype_mut.add_argument(
        "--post",
        action="store_const",
        const="post",
        dest="bump_type",
        help="Enter a post-release cycle.",
    )
    _btype_mut.add_argument(
        "--dev",
        action="store_const",
        const="dev",
        dest="bump_type",
        help="Increment the dev number.",
    )
    bump_parser.set_defaults(func=cmd_bump)

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

    # wheels
    wheels_parser = subparsers.add_parser("wheels", help=_H)
    wheels_parser.add_argument(
        "package",
        help="Install spec: ORG/REPO/PKG[@VERSION]",
    )
    wheels_parser.add_argument(
        "--release-tag",
        default=None,
        help="Download from a GitHub release tag.",
    )
    wheels_parser.add_argument(
        "--run-id",
        default=None,
        help="Download from a GitHub Actions run's artifacts.",
    )
    wheels_parser.add_argument(
        "-o",
        "--output",
        default="dist",
        help="Directory to save wheels into (default: dist/).",
    )
    wheels_parser.set_defaults(func=cmd_wheels)

    # init
    init_parser = subparsers.add_parser("init", help=_H)
    init_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory to write the workflow file (default: %(default)s).",
    )
    _init_mut = init_parser.add_mutually_exclusive_group()
    _init_mut.add_argument(
        "--force",
        action="store_true",
        help="Overwrite release.yml without preserving existing hooks.",
    )
    _init_mut.add_argument(
        "--upgrade",
        action="store_true",
        help="Upgrade frozen template fields in an existing release.yml.",
    )
    _init_mut.add_argument(
        "--base-only",
        action="store_true",
        help="Write merge bases to .uvr/bases/ without touching actual files.",
    )
    init_parser.add_argument(
        "--editor",
        help="Editor to use for conflict resolution (e.g. 'code', 'vim').",
    )

    def _cmd_init_dispatch(a: argparse.Namespace) -> None:
        if getattr(a, "upgrade", False):
            cmd_upgrade(a)
        else:
            cmd_init(a)

    init_parser.set_defaults(func=_cmd_init_dispatch)

    # validate
    validate_parser = subparsers.add_parser("validate", help=_H)
    validate_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Workflow directory (default: %(default)s).",
    )
    validate_parser.add_argument(
        "--diff",
        action="store_true",
        help="Show unified diff between current workflow and template.",
    )
    validate_parser.set_defaults(func=cmd_validate)

    # skill (subcommand group)
    skill_parser = subparsers.add_parser(
        "skill",
        help=_H,
        description="Manage Claude Code skills bundled with uvr.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    skill_sub = skill_parser.add_subparsers(
        dest="skill_command", required=True, title=argparse.SUPPRESS, metavar=""
    )
    skill_init_parser = skill_sub.add_parser(
        "init",
        help="Copy Claude skills to .claude/skills/",
        description="Copy bundled Claude Code skills into your project.",
    )
    _skill_mut = skill_init_parser.add_mutually_exclusive_group()
    _skill_mut.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing skill files.",
    )
    _skill_mut.add_argument(
        "--upgrade",
        action="store_true",
        help="Three-way merge bundled skills into existing files.",
    )
    _skill_mut.add_argument(
        "--base-only",
        action="store_true",
        help="Write merge bases to .uvr/bases/ without touching actual files.",
    )
    skill_init_parser.add_argument(
        "--editor",
        help="Editor to use for conflict resolution (e.g. 'code', 'vim').",
    )

    def _cmd_skill_dispatch(a: argparse.Namespace) -> None:
        if getattr(a, "upgrade", False):
            cmd_skill_upgrade(a)
        else:
            cmd_skill_init(a)

    skill_init_parser.set_defaults(func=_cmd_skill_dispatch)

    # -- CI steps ------------------------------------------------------

    def _cmd_validate_plan(a: argparse.Namespace) -> None:
        import json

        plan = ReleasePlan.model_validate_json(_resolve_plan_json(a.plan))
        print(json.dumps(plan.model_dump(mode="json"), indent=2))

    vp_parser = subparsers.add_parser("validate-plan", help=_H)
    vp_parser.add_argument(
        "--plan",
        default=None,
        help="Plan JSON, @file path, or omit to use UVR_PLAN env var.",
    )
    vp_parser.set_defaults(func=_cmd_validate_plan)

    def _cmd_build(a: argparse.Namespace) -> None:
        from pathlib import Path
        from ..shared.hooks import load_hook

        plan_obj = ReleasePlan.model_validate_json(_resolve_plan_json(a.plan))
        hook = load_hook(Path.cwd())
        ReleaseExecutor(plan_obj, hook).build(runner=a.runner)

    build_parser = subparsers.add_parser("build", help=_H)
    build_parser.add_argument(
        "--plan",
        default=None,
        help="Plan JSON, @file path, or omit to use UVR_PLAN env var.",
    )
    build_parser.add_argument("--runner", required=True)
    build_parser.set_defaults(func=_cmd_build)

    def _cmd_finalize(a: argparse.Namespace) -> None:
        from pathlib import Path
        from ..shared.hooks import load_hook

        plan_obj = ReleasePlan.model_validate_json(_resolve_plan_json(a.plan))
        hook = load_hook(Path.cwd())
        ReleaseExecutor(plan_obj, hook).finalize()

    finalize_parser = subparsers.add_parser("finalize", help=_H)
    finalize_parser.add_argument(
        "--plan",
        default=None,
        help="Plan JSON, @file path, or omit to use UVR_PLAN env var.",
    )
    finalize_parser.set_defaults(func=_cmd_finalize)

    # -- Low-level -----------------------------------------------------

    def _cmd_pin_deps(a: argparse.Namespace) -> None:
        from pathlib import Path
        from ..shared.utils.dependencies import pin_dependencies

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
