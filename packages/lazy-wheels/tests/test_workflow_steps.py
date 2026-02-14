"""Tests for lazy_wheels.workflow_steps."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lazy_wheels.models import PackageInfo
from lazy_wheels.workflow_steps import build_one, plan


@patch("lazy_wheels.workflow_steps.find_next_release_tag")
@patch("lazy_wheels.workflow_steps.find_last_tags")
@patch("lazy_wheels.workflow_steps.detect_changes")
@patch("lazy_wheels.workflow_steps.discover_packages")
def test_plan_writes_expected_outputs(
    mock_discover: MagicMock,
    mock_detect: MagicMock,
    mock_find_last: MagicMock,
    mock_find_next: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """plan writes changed/unchanged/last_tags/release to GITHUB_OUTPUT."""
    mock_discover.return_value = {
        "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[]),
        "pkg-b": PackageInfo(path="packages/b", version="1.0.0", deps=[]),
    }
    mock_find_last.return_value = {"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v1.0.0"}
    mock_detect.return_value = ["pkg-a"]
    mock_find_next.return_value = "r7"
    output_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.delenv("INPUT_RELEASE", raising=False)
    monkeypatch.setenv("FORCE_ALL", "false")

    plan()

    raw = output_file.read_text()
    assert 'changed=["pkg-a"]' in raw
    assert 'unchanged=["pkg-b"]' in raw
    assert 'last_tags={"pkg-a": "pkg-a/v1.0.0", "pkg-b": "pkg-b/v1.0.0"}' in raw
    assert "release=r7" in raw


@patch("lazy_wheels.workflow_steps.build_packages")
@patch("lazy_wheels.workflow_steps.discover_packages")
def test_build_one_skips_unchanged_package(
    mock_discover: MagicMock,
    mock_build: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_one is a no-op when PACKAGE is not in CHANGED list."""
    mock_discover.return_value = {
        "pkg-a": PackageInfo(path="packages/a", version="1.0.0", deps=[])
    }
    monkeypatch.setenv("PACKAGE", "pkg-a")
    monkeypatch.setenv("CHANGED", json.dumps(["pkg-b"]))

    build_one()

    mock_build.assert_not_called()
