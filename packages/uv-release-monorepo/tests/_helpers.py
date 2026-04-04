"""Shared test helpers (non-fixture functions used across test files)."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from uv_release_monorepo.cli import __version__, cmd_init
from uv_release_monorepo.shared.context import ReleaseContext
from uv_release_monorepo.shared.models import ChangedPackage, PackageInfo, ReleasePlan


def _write_workspace_repo(root: Path, package_names: list[str]) -> None:
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
    )
    for package_name in package_names:
        package_dir = root / "packages" / package_name
        package_dir.mkdir(parents=True)
        (package_dir / "pyproject.toml").write_text(
            f'[project]\nname = "{package_name}"\nversion = "1.0.0"\n'
        )


def _make_plan(
    changed: list[str] | None = None, unchanged: list[str] | None = None
) -> ReleasePlan:
    """Helper to create a ReleasePlan for testing."""
    changed = changed or []
    unchanged = unchanged or []
    changed_pkgs = {
        name: ChangedPackage(
            path=f"packages/{name}",
            version="1.0.0",
            deps=[],
            current_version="1.0.0",
            release_version="1.0.0",
            next_version="1.0.1.dev0",
            runners=[["ubuntu-latest"]],
        )
        for name in changed
    }
    unchanged_pkgs = {
        name: PackageInfo(path=f"packages/{name}", version="1.0.0", deps=[])
        for name in unchanged
    }
    return ReleasePlan(
        uvr_version=__version__,
        rebuild_all=False,
        changed=changed_pkgs,
        unchanged=unchanged_pkgs,
    )


def _init_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a workspace with a generated release.yml and return its path."""
    _write_workspace_repo(tmp_path, ["pkg-alpha"])
    monkeypatch.chdir(tmp_path)
    cmd_init(argparse.Namespace(workflow_dir=".github/workflows"))
    return tmp_path / ".github" / "workflows" / "release.yml"


def _runners_args(**kwargs: object) -> argparse.Namespace:
    """Build a cmd_runners Namespace with sensible defaults."""
    defaults: dict[str, object] = dict(
        package=None,
        add_runners=None,
        remove_runners=None,
        clear=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_ctx(
    packages: dict[str, PackageInfo],
    release_tags: dict[str, str | None] | None = None,
    baselines: dict[str, str | None] | None = None,
) -> ReleaseContext:
    """Build a fake ReleaseContext for tests."""
    if release_tags is None:
        release_tags = {n: None for n in packages}
    if baselines is None:
        baselines = {n: None for n in packages}
    mock_repo = MagicMock()
    mock_repo.references.get.return_value = None  # no tag conflicts by default
    return ReleaseContext(
        repo=mock_repo,
        packages=packages,
        baselines=baselines,
        release_tags=release_tags,
    )
