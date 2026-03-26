"""Tests for CLI argument parsing."""

from __future__ import annotations

import sys
from unittest.mock import patch

from uv_release_monorepo.cli import cli


def test_cli_dry_run_is_valid_arg() -> None:
    """--dry-run is a recognized argument for the release subcommand."""
    with patch.object(sys, "argv", ["uvr", "release", "--dry-run"]):
        with patch("uv_release_monorepo.cli.cmd_release") as mock_release:
            cli()
            args = mock_release.call_args[0][0]
            assert args.dry_run is True


def test_cli_where_defaults_to_ci() -> None:
    """--where defaults to 'ci'."""
    with patch.object(sys, "argv", ["uvr", "release"]):
        with patch("uv_release_monorepo.cli.cmd_release") as mock_release:
            cli()
            args = mock_release.call_args[0][0]
            assert args.where == "ci"


def test_cli_where_local() -> None:
    """--where local is accepted."""
    with patch.object(sys, "argv", ["uvr", "release", "--where", "local"]):
        with patch("uv_release_monorepo.cli.cmd_release") as mock_release:
            cli()
            args = mock_release.call_args[0][0]
            assert args.where == "local"
