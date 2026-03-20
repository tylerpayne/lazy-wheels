"""Tests for uv_release_monorepo.workflow_steps."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uv_release_monorepo.models import MatrixEntry, PackageInfo, ReleasePlan
from uv_release_monorepo.workflow_steps import (
    SCHEMA_VERSION,
    _parse_package_list,
    _parse_release_tags,
    build,
    discover,
    execute_build,
    execute_fetch_unchanged,
    execute_finalize,
    execute_publish_releases,
    execute_release,
    main,
)


@patch("uv_release_monorepo.workflow_steps.find_dev_baselines")
@patch("uv_release_monorepo.workflow_steps.find_release_tags")
@patch("uv_release_monorepo.workflow_steps.detect_changes")
@patch("uv_release_monorepo.workflow_steps.discover_packages")
def test_discover_writes_expected_outputs(
    mock_discover: MagicMock,
    mock_detect: MagicMock,
    mock_find_release: MagicMock,
    mock_find_dev: MagicMock,
    tmp_path: Path,
) -> None:
    """discover writes changed/unchanged/release_tags to output file."""
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
    output_file = tmp_path / "github_output.txt"

    discover(force_all=False, github_output=str(output_file))

    raw = output_file.read_text()
    assert 'changed=["pkg-a"]' in raw
    assert 'unchanged=["pkg-b"]' in raw
    assert 'release_tags={"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v1.0.0"}' in raw


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

    mock_discover.assert_called_once_with(False, "/tmp/out")


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


@patch("uv_release_monorepo.workflow_steps.find_dev_baselines")
@patch("uv_release_monorepo.workflow_steps.find_release_tags")
@patch("uv_release_monorepo.workflow_steps.detect_changes")
@patch("uv_release_monorepo.workflow_steps.discover_packages")
def test_discover_writes_schema_version(
    mock_discover: MagicMock,
    mock_detect: MagicMock,
    mock_find_release: MagicMock,
    mock_find_dev: MagicMock,
    tmp_path: Path,
) -> None:
    """discover writes schema_version to output file."""
    mock_discover.return_value = {
        "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
    }
    mock_find_release.return_value = {"pkg-a": "pkg-a/v1.0.0"}
    mock_find_dev.return_value = {"pkg-a": "pkg-a/v1.0.0-dev"}
    mock_detect.return_value = ["pkg-a"]
    output_file = tmp_path / "github_output.txt"

    discover(force_all=False, github_output=str(output_file))

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


def _make_plan_json(changed: list[str], unchanged: list[str]) -> str:
    """Helper to build a minimal ReleasePlan JSON string."""
    all_pkgs = changed + unchanged
    packages = {
        name: PackageInfo(path=f"packages/{name}", version="1.0.0", deps=[])
        for name in all_pkgs
    }
    plan = ReleasePlan(
        uvr_version="0.3.0",
        force_all=False,
        changed={name: packages[name] for name in changed},
        unchanged={name: packages[name] for name in unchanged},
        release_tags={name: None for name in all_pkgs},
        matrix=[MatrixEntry(package=name, runner="ubuntu-latest") for name in changed],
    )
    return plan.model_dump_json()


@patch("uv_release_monorepo.workflow_steps.build_packages")
def test_execute_build_builds_changed_package(mock_build: MagicMock) -> None:
    """execute_build calls build_packages when package is in changed."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_build(plan_json, "pkg-a")
    mock_build.assert_called_once()


@patch("uv_release_monorepo.workflow_steps.build_packages")
def test_execute_build_skips_unchanged_package(mock_build: MagicMock) -> None:
    """execute_build is a no-op when package is not in changed."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_build(plan_json, "pkg-b")
    mock_build.assert_not_called()


@patch("uv_release_monorepo.workflow_steps.tag_dev_baselines")
@patch("uv_release_monorepo.workflow_steps.commit_bumps")
@patch("uv_release_monorepo.workflow_steps.bump_versions")
@patch("uv_release_monorepo.workflow_steps.tag_changed_packages")
@patch("uv_release_monorepo.workflow_steps.publish_release")
@patch("uv_release_monorepo.workflow_steps.fetch_unchanged_wheels")
@patch("uv_release_monorepo.workflow_steps.collect_published_state")
def test_execute_release_calls_full_sequence(
    mock_collect: MagicMock,
    mock_fetch: MagicMock,
    mock_publish: MagicMock,
    mock_tag_pkg: MagicMock,
    mock_bump: MagicMock,
    mock_commit: MagicMock,
    mock_tag_dev: MagicMock,
) -> None:
    """execute_release runs the full post-build release sequence."""
    mock_bump.return_value = {}
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_release(plan_json)

    mock_collect.assert_called_once()
    mock_fetch.assert_called_once()
    mock_publish.assert_called_once()
    mock_tag_pkg.assert_called_once()
    mock_bump.assert_called_once()
    mock_commit.assert_called_once()
    mock_tag_dev.assert_called_once()


@patch("uv_release_monorepo.workflow_steps.execute_build")
def test_main_dispatches_execute_build(mock_exec_build: MagicMock) -> None:
    """main dispatches execute-build subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["execute-build", "--plan", plan_json, "--package", "pkg-a"])
    mock_exec_build.assert_called_once_with(plan_json, "pkg-a")


@patch("uv_release_monorepo.workflow_steps.execute_release")
def test_main_dispatches_execute_release(mock_exec_release: MagicMock) -> None:
    """main dispatches execute-release subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["execute-release", "--plan", plan_json])
    mock_exec_release.assert_called_once_with(plan_json)


@patch("uv_release_monorepo.workflow_steps.fetch_unchanged_wheels")
def test_execute_fetch_unchanged_calls_fetch(mock_fetch: MagicMock) -> None:
    """execute_fetch_unchanged calls fetch_unchanged_wheels with plan data."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_fetch_unchanged(plan_json)
    mock_fetch.assert_called_once()


@patch("uv_release_monorepo.workflow_steps.publish_release")
def test_execute_publish_releases_calls_publish(mock_publish: MagicMock) -> None:
    """execute_publish_releases calls publish_release with plan data."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_publish_releases(plan_json)
    mock_publish.assert_called_once()


@patch("uv_release_monorepo.workflow_steps.tag_dev_baselines")
@patch("uv_release_monorepo.workflow_steps.commit_bumps")
@patch("uv_release_monorepo.workflow_steps.bump_versions")
@patch("uv_release_monorepo.workflow_steps.tag_changed_packages")
@patch("uv_release_monorepo.workflow_steps.collect_published_state")
def test_execute_finalize_calls_sequence(
    mock_collect: MagicMock,
    mock_tag_pkg: MagicMock,
    mock_bump: MagicMock,
    mock_commit: MagicMock,
    mock_tag_dev: MagicMock,
) -> None:
    """execute_finalize runs the tag/bump/commit/tag-dev sequence."""
    mock_bump.return_value = {}
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=["pkg-b"])
    execute_finalize(plan_json)

    mock_collect.assert_called_once()
    mock_tag_pkg.assert_called_once()
    mock_bump.assert_called_once()
    mock_commit.assert_called_once()
    mock_tag_dev.assert_called_once()


@patch("uv_release_monorepo.workflow_steps.execute_fetch_unchanged")
def test_main_dispatches_fetch_unchanged(mock_fetch: MagicMock) -> None:
    """main dispatches fetch-unchanged subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["fetch-unchanged", "--plan", plan_json])
    mock_fetch.assert_called_once_with(plan_json)


@patch("uv_release_monorepo.workflow_steps.execute_publish_releases")
def test_main_dispatches_publish_releases(mock_publish: MagicMock) -> None:
    """main dispatches publish-releases subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["publish-releases", "--plan", plan_json])
    mock_publish.assert_called_once_with(plan_json)


@patch("uv_release_monorepo.workflow_steps.execute_finalize")
def test_main_dispatches_finalize(mock_finalize: MagicMock) -> None:
    """main dispatches finalize subcommand."""
    plan_json = _make_plan_json(changed=["pkg-a"], unchanged=[])
    main(["finalize", "--plan", plan_json])
    mock_finalize.assert_called_once_with(plan_json)
