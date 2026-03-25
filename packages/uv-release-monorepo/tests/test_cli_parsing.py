"""Tests for CLI argument parsing."""

from __future__ import annotations

import sys
from unittest.mock import patch

from uv_release_monorepo.cli import cli


def test_cli_dry_run_is_valid_arg() -> None:
    """--dry-run is a recognized argument for the run subcommand."""
    with patch.object(sys, "argv", ["uvr", "run", "--dry-run"]):
        with patch("uv_release_monorepo.cli.cmd_run") as mock_run:
            cli()
            args = mock_run.call_args[0][0]
            assert args.dry_run is True
