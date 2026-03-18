"""Tests for bundled templates."""

from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent / "uv_release_monorepo" / "templates"
)


def test_release_template_has_preamble() -> None:
    template = (TEMPLATES_DIR / "release.yml").read_text()

    assert "Generated with uv-release-monorepo" in template
    assert "https://github.com/tylerpayne/uv-release-monorepo" in template
    assert "uv tool install uv-release-monorepo" in template
    assert "uvr release" in template


def test_release_template_has_uvr_version_input() -> None:
    template = (TEMPLATES_DIR / "release.yml").read_text()

    assert "uvr_version" in template
    assert "uv-release-monorepo=={0}" in template
    assert "__UVR_VERSION__" not in template


def test_release_matrix_template_has_preamble() -> None:
    template = (TEMPLATES_DIR / "release-matrix.yml").read_text()

    assert "Generated with uv-release-monorepo" in template
    assert "https://github.com/tylerpayne/uv-release-monorepo" in template
    assert "uv tool install uv-release-monorepo" in template
    assert "uvr init -m" in template
    assert "uvr release" in template


def test_release_matrix_template_has_uvr_version_input() -> None:
    template = (TEMPLATES_DIR / "release-matrix.yml").read_text()

    assert "uvr_version" in template
    # Matrix template has 3 jobs that each install uv-release-monorepo
    assert template.count("uv-release-monorepo=={0}") == 3
    assert "__UVR_VERSION__" not in template
