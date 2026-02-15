"""Tests for bundled templates."""

from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "lazy_wheels" / "templates"


def test_release_template_has_lazy_wheels_preamble() -> None:
    template = (TEMPLATES_DIR / "release.yml").read_text()

    assert "Generated with lazy-wheels" in template
    assert "https://github.com/tylerpayne/lazy-wheels" in template
    assert "uv tool install lazy-wheels" in template
    assert "lazy-wheels release" in template


def test_release_matrix_template_has_lazy_wheels_preamble() -> None:
    template = (TEMPLATES_DIR / "release-matrix.yml").read_text()

    assert "Generated with lazy-wheels" in template
    assert "https://github.com/tylerpayne/lazy-wheels" in template
    assert "uv tool install lazy-wheels" in template
    assert "lazy-wheels init -m" in template
    assert "lazy-wheels release" in template
