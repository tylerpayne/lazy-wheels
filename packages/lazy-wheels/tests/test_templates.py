"""Tests for bundled templates."""

from __future__ import annotations

from pathlib import Path


def test_release_template_has_lazy_wheels_preamble() -> None:
    template = (
        Path(__file__).resolve().parent.parent / "lazy_wheels" / "release.yml"
    ).read_text()

    assert "Generated with lazy-wheels" in template
    assert "https://github.com/tylerpayne/lazy-wheels" in template
    assert "uv tool install lazy-wheels" in template
    assert "lazy-wheels release" in template
