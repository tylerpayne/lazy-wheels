"""Tests for uv_release_monorepo.workflow_steps."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.models import PackageInfo
from uv_release_monorepo.workflow_steps import (
    SCHEMA_VERSION,
    _parse_package_list,
    _parse_release_tags,
    build,
    discover,
    main,
)


@patch("uv_release_monorepo.workflow_steps.find_next_release_tag")
@patch("uv_release_monorepo.workflow_steps.find_dev_baselines")
@patch("uv_release_monorepo.workflow_steps.find_release_tags")
@patch("uv_release_monorepo.workflow_steps.detect_changes")
@patch("uv_release_monorepo.workflow_steps.discover_packages")
def test_discover_writes_expected_outputs(
    mock_discover: MagicMock,
    mock_detect: MagicMock,
    mock_find_release: MagicMock,
    mock_find_dev: MagicMock,
    mock_find_next: MagicMock,
    tmp_path: Path,
) -> None:
    """discover writes changed/unchanged/release_tags/release to output file."""
    mock_discover.return_value = {
        "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
        "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
    }
    mock_find_release.return_value = {"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v1.0.0"}
    mock_find_dev.return_value = {
        "pkg-a": "pkg-a/v1.0.0-dev",
        "pkg-b": "pkg-b/v1.0.0-dev",
    }
    mock_detect.return_value = ["pkg-a"]
    mock_find_next.return_value = "r7"
    output_file = tmp_path / "github_output.txt"

    discover(None, force_all=False, github_output=str(output_file))

    raw = output_file.read_text()
    assert 'changed=["pkg-a"]' in raw
    assert 'unchanged=["pkg-b"]' in raw
    assert 'release_tags={"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v1.0.0"}' in raw
    assert "release=r7" in raw


@patch("uv_release_monorepo.workflow_steps.build_packages")
@patch("uv_release_monorepo.workflow_steps.discover_packages")
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


def test_build_rejects_invalid_changed_json() -> None:
    """build returns clear error for malformed JSON input."""
    with pytest.raises(SystemExit, match="Invalid JSON for --changed"):
        build("pkg-a", "{not-json")


@patch("uv_release_monorepo.workflow_steps.discover")
def test_main_dispatches_discover_from_cli_arg(mock_discover: MagicMock) -> None:
    """main dispatches discover handler from CLI args."""
    main(["discover", "--github-output", "/tmp/out"])

    mock_discover.assert_called_once_with(None, False, "/tmp/out")


@patch("uv_release_monorepo.workflow_steps.build")
def test_main_dispatches_build(mock_build: MagicMock) -> None:
    """main dispatches build handler from CLI args."""
    main(["build", "--package", "pkg-a", "--changed", '["pkg-a"]'])

    mock_build.assert_called_once_with("pkg-a", '["pkg-a"]')


def test_main_requires_step_arg(capsys: pytest.CaptureFixture[str]) -> None:
    """main errors when no step arg is provided."""
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2
    assert "required: command" in capsys.readouterr().err


def test_main_rejects_unknown_step(capsys: pytest.CaptureFixture[str]) -> None:
    """main errors on unknown step arg."""
    with pytest.raises(SystemExit) as excinfo:
        main(["not-a-step"])
    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_schema_version_is_int() -> None:
    """SCHEMA_VERSION is a positive integer."""
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1


@patch("uv_release_monorepo.workflow_steps.find_next_release_tag")
@patch("uv_release_monorepo.workflow_steps.find_dev_baselines")
@patch("uv_release_monorepo.workflow_steps.find_release_tags")
@patch("uv_release_monorepo.workflow_steps.detect_changes")
@patch("uv_release_monorepo.workflow_steps.discover_packages")
def test_discover_writes_schema_version(
    mock_discover: MagicMock,
    mock_detect: MagicMock,
    mock_find_release: MagicMock,
    mock_find_dev: MagicMock,
    mock_find_next: MagicMock,
    tmp_path: Path,
) -> None:
    """discover writes schema_version to output file."""
    mock_discover.return_value = {
        "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
    }
    mock_find_release.return_value = {"pkg-a": "pkg-a/v1.0.0"}
    mock_find_dev.return_value = {"pkg-a": "pkg-a/v1.0.0-dev"}
    mock_detect.return_value = ["pkg-a"]
    mock_find_next.return_value = "r1"
    output_file = tmp_path / "github_output.txt"

    discover(None, force_all=False, github_output=str(output_file))

    raw = output_file.read_text()
    assert f"schema_version={SCHEMA_VERSION}" in raw


def test_parse_package_list_accepts_list() -> None:
    """_parse_package_list accepts a valid JSON array."""
    result = _parse_package_list('["pkg-a", "pkg-b"]', arg_name="--changed")
    assert result == ["pkg-a", "pkg-b"]


def test_parse_package_list_rejects_non_list() -> None:
    """_parse_package_list raises SystemExit for non-array JSON."""
    with pytest.raises(SystemExit, match="expected JSON array"):
        _parse_package_list('{"not": "a list"}', arg_name="--changed")


def test_parse_package_list_rejects_invalid_json() -> None:
    """_parse_package_list raises SystemExit for invalid JSON."""
    with pytest.raises(SystemExit, match="Invalid JSON for --changed"):
        _parse_package_list("{bad json", arg_name="--changed")


def test_parse_release_tags_accepts_dict() -> None:
    """_parse_release_tags accepts a valid JSON object."""
    result = _parse_release_tags(
        '{"pkg-a": "pkg-a/v1.0.0", "pkg-b": null}', arg_name="--release-tags"
    )
    assert result == {"pkg-a": "pkg-a/v1.0.0", "pkg-b": None}


def test_parse_release_tags_rejects_non_dict() -> None:
    """_parse_release_tags raises SystemExit for non-object JSON."""
    with pytest.raises(SystemExit, match="expected JSON object"):
        _parse_release_tags('["pkg-a"]', arg_name="--release-tags")
