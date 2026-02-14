"""Tests for lazy_wheels.workflow_steps."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lazy_wheels.models import PackageInfo
from lazy_wheels.workflow_steps import build, discover, main


@patch("lazy_wheels.workflow_steps.find_next_release_tag")
@patch("lazy_wheels.workflow_steps.find_last_tags")
@patch("lazy_wheels.workflow_steps.detect_changes")
@patch("lazy_wheels.workflow_steps.discover_packages")
def test_discover_writes_expected_outputs(
    mock_discover: MagicMock,
    mock_detect: MagicMock,
    mock_find_last: MagicMock,
    mock_find_next: MagicMock,
    tmp_path: Path,
) -> None:
    """discover writes changed/unchanged/last_tags/release to output file."""
    mock_discover.return_value = {
        "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
        "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
    }
    mock_find_last.return_value = {"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v1.0.0"}
    mock_detect.return_value = ["pkg-a"]
    mock_find_next.return_value = "r7"
    output_file = tmp_path / "github_output.txt"

    discover(None, force_all=False, github_output=str(output_file))

    raw = output_file.read_text()
    assert 'changed=["pkg-a"]' in raw
    assert 'unchanged=["pkg-b"]' in raw
    assert 'last_tags={"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v1.0.0"}' in raw
    assert "release=r7" in raw


@patch("lazy_wheels.workflow_steps.build_packages")
@patch("lazy_wheels.workflow_steps.discover_packages")
def test_build_skips_unchanged_package(
    mock_discover: MagicMock,
    mock_build: MagicMock,
) -> None:
    """build is a no-op when package is not in changed list."""
    mock_discover.return_value = {
        "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])
    }

    build("pkg-a", json.dumps(["pkg-b"]))

    mock_build.assert_not_called()


@patch("lazy_wheels.workflow_steps.discover")
def test_main_dispatches_discover_from_cli_arg(mock_discover: MagicMock) -> None:
    """main dispatches discover handler from CLI args."""
    main(["discover", "--github-output", "/tmp/out"])

    mock_discover.assert_called_once_with(None, False, "/tmp/out")


@patch("lazy_wheels.workflow_steps.build")
def test_main_dispatches_build(mock_build: MagicMock) -> None:
    """main dispatches build handler from CLI args."""
    main(["build", "--package", "pkg-a", "--changed", '["pkg-a"]'])

    mock_build.assert_called_once_with("pkg-a", '["pkg-a"]')


def test_main_requires_step_arg() -> None:
    """main errors when no step arg is provided."""
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2


def test_main_rejects_unknown_step() -> None:
    """main errors on unknown step arg."""
    with pytest.raises(SystemExit) as excinfo:
        main(["not-a-step"])
    assert excinfo.value.code == 2
