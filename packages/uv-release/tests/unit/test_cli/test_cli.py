"""Tests for CLI argument parsing and PlanParams construction."""

from __future__ import annotations

import argparse

import pytest

from uv_release.cli import build_parser
from uv_release.cli.status import StatusArgs
from uv_release.cli.build import BuildArgs
from uv_release.cli.bump import BumpArgs
from uv_release.cli.release import ReleaseArgs
from uv_release.types import BumpType


class TestParserConstruction:
    """Smoke tests that the argparse parser builds and parses without error."""

    def test_build_parser(self) -> None:
        """Parser construction succeeds (catches invalid kwargs like intent=)."""
        parser = build_parser()
        assert parser is not None

    @pytest.mark.parametrize(
        "argv,expected_command",
        [
            (["status"], "status"),
            (["build"], "build"),
            (["release", "--dry-run"], "release"),
            (["bump", "--minor"], "bump"),
            (["clean"], "clean"),
            (["workflow", "init"], "workflow"),
            (["workflow", "validate"], "workflow"),
            (["skill", "init"], "skill"),
            (["install"], "install"),
            (["download"], "download"),
            (["jobs", "build"], "jobs"),
        ],
    )
    def test_parse_subcommands(self, argv: list[str], expected_command: str) -> None:
        """Each subcommand parses minimal valid argv."""
        parser = build_parser()
        args = parser.parse_args(argv)
        assert args.command == expected_command


class TestStatusArgs:
    def test_defaults(self) -> None:
        ns = argparse.Namespace(
            command="status", func=None, rebuild_all=False, rebuild=None
        )
        parsed = StatusArgs.from_namespace(ns)
        assert parsed.rebuild_all is False
        assert parsed.rebuild is None

    def test_rebuild_all(self) -> None:
        ns = argparse.Namespace(
            command="status", func=None, rebuild_all=True, rebuild=None
        )
        parsed = StatusArgs.from_namespace(ns)
        assert parsed.rebuild_all is True


class TestBuildArgs:
    def test_defaults(self) -> None:
        ns = argparse.Namespace(
            command="build", func=None, rebuild_all=False, packages=None
        )
        parsed = BuildArgs.from_namespace(ns)
        assert parsed.rebuild_all is False
        assert parsed.packages is None

    def test_with_packages(self) -> None:
        ns = argparse.Namespace(
            command="build", func=None, rebuild_all=False, packages=["alpha", "beta"]
        )
        parsed = BuildArgs.from_namespace(ns)
        assert parsed.packages == ["alpha", "beta"]


class TestBumpArgs:
    def test_minor_bump(self) -> None:
        ns = argparse.Namespace(
            command="bump",
            func=None,
            bump_all=False,
            packages=None,
            force=False,
            no_pin=False,  # CLI negative, inverted to pin=True in PlanParams
            bump_type="minor",
        )
        parsed = BumpArgs.from_namespace(ns)
        assert parsed.bump_type == "minor"
        assert BumpType(parsed.bump_type) == BumpType.MINOR

    def test_all_flag(self) -> None:
        ns = argparse.Namespace(
            command="bump",
            func=None,
            bump_all=True,
            packages=None,
            force=False,
            no_pin=True,
            bump_type="major",
        )
        parsed = BumpArgs.from_namespace(ns)
        assert parsed.bump_all is True
        assert parsed.no_pin is True


class TestReleaseArgs:
    def test_defaults(self) -> None:
        ns = argparse.Namespace(
            command="release",
            func=None,
            where="ci",
            dry_run=False,
            plan=None,
            rebuild_all=False,
            rebuild=None,
            dev=False,
            yes=False,
            skip=None,
            no_push=False,
            json_output=False,
            release_notes=None,
        )
        parsed = ReleaseArgs.from_namespace(ns)
        assert parsed.where == "ci"
        assert parsed.dev is False

    def test_local_dev_release(self) -> None:
        ns = argparse.Namespace(
            command="release",
            func=None,
            where="local",
            dry_run=True,
            plan=None,
            rebuild_all=False,
            rebuild=None,
            dev=True,
            yes=False,
            skip=["publish"],
            no_push=True,
            json_output=False,
            release_notes=None,
        )
        parsed = ReleaseArgs.from_namespace(ns)
        assert parsed.where == "local"
        assert parsed.dev is True
        assert parsed.skip == ["publish"]
        assert parsed.no_push is True
