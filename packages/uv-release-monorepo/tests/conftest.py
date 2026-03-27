"""Shared test fixtures and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from tests._helpers import (  # noqa: F401 — re-export for convenience
    _init_workflow,
    _make_plan,
    _runners_args,
    _write_workspace_repo,
)


@pytest.fixture(autouse=True)
def _no_git_commit_and_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent init/skill from prompting for commits during tests."""
    noop = lambda *a, **kw: None  # noqa: E731
    monkeypatch.setattr("uv_release_monorepo.cli.init._git_commit_and_record", noop)
    monkeypatch.setattr("uv_release_monorepo.cli.skill._git_commit_and_record", noop)


@pytest.fixture
def tmp_pyproject(tmp_path: Path) -> Path:
    """Create a temporary pyproject.toml file."""
    content = """\
[project]
name = "test-package"
version = "1.0.0"
dependencies = [
    "requests>=2.0",
    "internal-dep>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "another-internal>=0.5"]

[dependency-groups]
test = ["pytest>=8.0", "group-internal>=0.1"]
"""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(content)
    return pyproject


@pytest.fixture
def sample_toml_doc() -> tomlkit.TOMLDocument:
    """Create a sample TOML document."""
    content = """\
[project]
name = "my-package"
version = "2.0.0"
dependencies = ["click>=8.0", "pydantic>=2.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
docs = ["sphinx>=7.0"]

[dependency-groups]
test = ["hypothesis>=6.0"]

[tool.uv.workspace]
members = ["packages/*", "libs/*"]
"""
    return tomlkit.parse(content)
