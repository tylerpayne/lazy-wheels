"""Argparse setup and main entry point for the uvr CLI."""

from __future__ import annotations

import argparse

from ..shared.utils.cli import __version__
from .bump import cmd_bump
from .clean import cmd_clean
from .init import cmd_init_dispatch, cmd_validate
from .install import cmd_install
from .release import cmd_release
from .runners import cmd_runners
from .skill import cmd_skill_dispatch
from .status import cmd_status
from .download import cmd_download


def cli() -> None:
    """Main CLI entry point."""
    _USAGE = """\
usage: uvr [-h] [--version] <command> ...

Lazy monorepo wheel builder — only rebuilds what changed.

Commands:
  release          Plan and execute a release (locally or via CI)
  status           Preview the release plan (allows dirty working tree)
  bump             Bump package versions in the workspace
  install          Install a package from GitHub releases (org/repo/pkg)
  download         Download wheels from GitHub releases or CI artifacts
  clean            Remove uvr caches and ephemeral files
  workflow init    Scaffold the GitHub Actions workflow
  workflow validate  Validate an existing release.yml
  workflow runners Manage per-package build runners
  skill init       Copy Claude Code skills into your project

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

    # release
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
        help="Execute a pre-computed release plan instead of generating one.",
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
    release_parser.add_argument(
        "--dev",
        action="store_const",
        const="dev",
        dest="release_type",
        help="Publish the .devN version as-is instead of stripping it.",
    )
    release_parser.add_argument(
        "--bump",
        choices=[
            "alpha",
            "beta",
            "rc",
            "post",
            "dev",
            "stable",
            "minor",
            "major",
            "patch",
        ],
        default=None,
        metavar="TYPE",
        help="Bump all packages before planning (e.g. --bump alpha).",
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
    _dispatch.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Workflow directory (default: %(default)s).",
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
    release_parser.add_argument(
        "--release-notes",
        nargs=2,
        action="append",
        metavar=("PKG", "NOTES"),
        help="Set release notes for a package. NOTES is inline text or @file.",
    )
    release_parser.set_defaults(func=cmd_release)

    # status
    status_parser = subparsers.add_parser("status", help=_H)
    status_parser.add_argument(
        "--rebuild-all",
        action="store_true",
        help="Show all packages as changed.",
    )
    status_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Workflow directory (default: %(default)s).",
    )
    status_parser.set_defaults(func=cmd_status)

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
    bump_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Skip the changed-package guard when using --package.",
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
    _btype_mut.add_argument(
        "--stable",
        action="store_const",
        const="stable",
        dest="bump_type",
        help="Strip pre-release markers: X.Y.Z.dev0",
    )
    bump_parser.set_defaults(func=cmd_bump)

    # install
    install_parser = subparsers.add_parser("install", help=_H)
    install_parser.add_argument(
        "package",
        help="Package name, optionally with version: PKG[@VERSION]",
    )
    install_parser.add_argument(
        "--repo",
        default=None,
        help="GitHub repository (ORG/REPO). Inferred from cwd if omitted.",
    )
    install_parser.add_argument(
        "--run-id",
        default=None,
        help="Install from a GitHub Actions run's artifacts instead of a release.",
    )
    install_parser.set_defaults(func=cmd_install)

    # download
    download_parser = subparsers.add_parser("download", help=_H)
    download_parser.add_argument(
        "package",
        nargs="?",
        default=None,
        help="Package name, optionally with version: PKG[@VERSION]. Optional with --run-id.",
    )
    download_parser.add_argument(
        "--repo",
        default=None,
        help="GitHub repository (ORG/REPO). Inferred from cwd if omitted.",
    )
    download_parser.add_argument(
        "--release-tag",
        default=None,
        help="Download from a GitHub release tag.",
    )
    download_parser.add_argument(
        "--run-id",
        default=None,
        help="Download from a GitHub Actions run's artifacts.",
    )
    download_parser.add_argument(
        "-o",
        "--output",
        default="dist",
        help="Directory to save wheels into (default: dist/).",
    )
    download_parser.add_argument(
        "--all-platforms",
        action="store_true",
        default=False,
        help="Download wheels for all platforms, not just the current one.",
    )
    download_parser.set_defaults(func=cmd_download)

    # clean
    clean_parser = subparsers.add_parser("clean", help=_H)
    clean_parser.set_defaults(func=cmd_clean)

    # -- workflow (init, validate, runners) ---------------------------------

    workflow_parser = subparsers.add_parser(
        "workflow",
        help=_H,
        description="Manage the release workflow and build runners.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    workflow_sub = workflow_parser.add_subparsers(
        dest="workflow_command", required=True, title=argparse.SUPPRESS, metavar=""
    )

    wf_init_parser = workflow_sub.add_parser(
        "init",
        help="Scaffold the GitHub Actions workflow.",
        description="Scaffold or upgrade the release.yml workflow file.",
    )
    wf_init_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Directory to write the workflow file (default: %(default)s).",
    )
    _init_mut = wf_init_parser.add_mutually_exclusive_group()
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
    wf_init_parser.add_argument(
        "--editor",
        help="Editor to use for conflict resolution (e.g. 'code', 'vim').",
    )
    wf_init_parser.set_defaults(func=cmd_init_dispatch)

    wf_validate_parser = workflow_sub.add_parser(
        "validate", help="Validate an existing release.yml."
    )
    wf_validate_parser.add_argument(
        "--workflow-dir",
        default=".github/workflows",
        help="Workflow directory (default: %(default)s).",
    )
    wf_validate_parser.add_argument(
        "--diff",
        action="store_true",
        help="Show unified diff between current workflow and template.",
    )
    wf_validate_parser.set_defaults(func=cmd_validate)

    wf_runners_parser = workflow_sub.add_parser(
        "runners", help="Manage per-package build runners."
    )
    wf_runners_parser.add_argument(
        "package",
        nargs="?",
        default=None,
        metavar="PKG",
        help="Package name (omit to show all).",
    )
    _rmut = wf_runners_parser.add_mutually_exclusive_group()
    _rmut.add_argument("--add", dest="add_value", metavar="RUNNER")
    _rmut.add_argument("--remove", dest="remove_value", metavar="RUNNER")
    _rmut.add_argument("--clear", action="store_true")
    wf_runners_parser.set_defaults(func=cmd_runners)

    # skill
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
    skill_init_parser.set_defaults(func=cmd_skill_dispatch)

    # -- jobs (CI steps) ---------------------------------------------------

    jobs_parser = subparsers.add_parser(
        "jobs",
        help=_H,
        description="CI workflow steps and low-level commands.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    jobs_sub = jobs_parser.add_subparsers(
        dest="jobs_command", required=True, title=argparse.SUPPRESS, metavar=""
    )

    from .jobs import (
        cmd_validate_plan,
        cmd_build,
        cmd_download as cmd_job_download,
        cmd_release as cmd_job_release,
        cmd_bump as cmd_job_bump,
    )

    vp_parser = jobs_sub.add_parser(
        "validate", help="Validate and pretty-print the release plan."
    )
    vp_parser.add_argument(
        "--plan",
        default=None,
        help="Plan JSON, @file path, or omit to use UVR_PLAN env var.",
    )
    vp_parser.set_defaults(func=cmd_validate_plan)

    build_parser = jobs_sub.add_parser("build", help="Build packages for a runner.")
    build_parser.add_argument(
        "--plan",
        default=None,
        help="Plan JSON, @file path, or omit to use UVR_PLAN env var.",
    )
    build_parser.add_argument("--runner", required=True)
    build_parser.set_defaults(func=cmd_build)

    download_job_parser = jobs_sub.add_parser(
        "download", help="Download wheels for changed packages."
    )
    download_job_parser.add_argument(
        "--plan",
        default=None,
        help="Plan JSON, @file path, or omit to use UVR_PLAN env var.",
    )
    download_job_parser.set_defaults(func=cmd_job_download)

    release_job_parser = jobs_sub.add_parser(
        "release", help="Tag, create GitHub releases, and push release tags."
    )
    release_job_parser.add_argument(
        "--plan",
        default=None,
        help="Plan JSON, @file path, or omit to use UVR_PLAN env var.",
    )
    release_job_parser.set_defaults(func=cmd_job_release)

    bump_job_parser = jobs_sub.add_parser(
        "bump", help="Bump versions, commit, baseline tags, and push."
    )
    bump_job_parser.add_argument(
        "--plan",
        default=None,
        help="Plan JSON, @file path, or omit to use UVR_PLAN env var.",
    )
    bump_job_parser.set_defaults(func=cmd_job_bump)

    # Split on "--" so extra args (e.g. for uv pip install) don't confuse argparse
    import sys as _sys

    argv = _sys.argv[1:]
    if "--" in argv:
        split = argv.index("--")
        main_argv = argv[:split]
        extra_argv = argv[split + 1 :]
    else:
        main_argv = argv
        extra_argv = []

    args = parser.parse_args(main_argv)
    args.pip_args = extra_argv
    args.func(args)
