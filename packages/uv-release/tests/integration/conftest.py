"""Shared fixtures for integration tests using real git repos."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal uv workspace with two packages and a real git repo.

    Layout:
        tmp_path/
            .git/
            pyproject.toml          (workspace root)
            packages/
                alpha/
                    pyproject.toml  (version 1.0.0.dev0)
                beta/
                    pyproject.toml  (version 1.0.0.dev0, depends on alpha)
                    src/
                        __init__.py
    """
    monkeypatch.chdir(tmp_path)

    # Root pyproject.toml
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "workspace"\nversion = "0.0.0"\n\n'
        "[tool.uv.workspace]\n"
        'members = ["packages/*"]\n'
    )

    # Package alpha
    alpha_dir = tmp_path / "packages" / "alpha"
    alpha_dir.mkdir(parents=True)
    (alpha_dir / "pyproject.toml").write_text(
        "[project]\n"
        'name = "alpha"\n'
        'version = "1.0.0.dev0"\n'
        "dependencies = []\n\n"
        "[build-system]\n"
        'requires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
    )
    alpha_src = alpha_dir / "alpha"
    alpha_src.mkdir()
    (alpha_src / "__init__.py").write_text("")

    # Package beta (depends on alpha)
    beta_dir = tmp_path / "packages" / "beta"
    beta_dir.mkdir(parents=True)
    (beta_dir / "pyproject.toml").write_text(
        "[project]\n"
        'name = "beta"\n'
        'version = "1.0.0.dev0"\n'
        'dependencies = ["alpha"]\n\n'
        "[build-system]\n"
        'requires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
    )
    beta_src = beta_dir / "beta"
    beta_src.mkdir()
    (beta_src / "__init__.py").write_text("")

    # Init git repo and make initial commit
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "initial commit")

    return tmp_path


def _git(cwd: Path, *args: str) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": "2025-01-01T00:00:00",
            "GIT_COMMITTER_DATE": "2025-01-01T00:00:00",
        },
    )
    return result.stdout.strip()


def add_baseline_tags(cwd: Path) -> None:
    """Tag current commit as the baseline for both packages."""
    _git(cwd, "tag", "alpha/v1.0.0.dev0-base")
    _git(cwd, "tag", "beta/v1.0.0.dev0-base")


def modify_file(cwd: Path, rel_path: str, content: str = "changed\n") -> None:
    """Write content to a file and commit it."""
    path = cwd / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    _git(cwd, "add", str(path))
    _git(cwd, "commit", "-m", f"modify {rel_path}")
