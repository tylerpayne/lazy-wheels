"""Shared test helpers (non-fixture functions used across test files)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from uv_release_monorepo.cli import __version__, cmd_init
from uv_release_monorepo.shared.models import MatrixEntry, PackageInfo, ReleasePlan


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
    all_pkgs = changed + unchanged
    packages = {
        name: PackageInfo(path=f"packages/{name}", version="1.0.0", deps=[])
        for name in all_pkgs
    }
    return ReleasePlan(
        uvr_version=__version__,
        rebuild_all=False,
        changed={name: packages[name] for name in changed},
        unchanged={name: packages[name] for name in unchanged},
        release_tags={name: None for name in all_pkgs},
        matrix=[
            MatrixEntry(
                package=name,
                runner=["ubuntu-latest"],
                path=f"packages/{name}",
                version="1.0.0",
            )
            for name in changed
        ],
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
        add_value=None,
        remove_value=None,
        clear=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)
