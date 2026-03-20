"""Tests for bundled templates."""

from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent / "uv_release_monorepo" / "templates"
)


def test_executor_template_has_preamble() -> None:
    template = (TEMPLATES_DIR / "release.yml").read_text()

    assert "Generated with uv-release-monorepo" in template
    assert "https://github.com/tylerpayne/uv-release-monorepo" in template
    assert "uv tool install uv-release-monorepo" in template
    assert "uvr release" in template


def test_executor_template_has_plan_input() -> None:
    template = (TEMPLATES_DIR / "release.yml").read_text()

    assert "plan:" in template
    assert "required: true" in template


def test_executor_template_has_uvr_version_input() -> None:
    template = (TEMPLATES_DIR / "release.yml").read_text()

    assert "uvr_version" in template
    assert "uv-release-monorepo=={0}" in template
    assert "__UVR_VERSION__" not in template


def test_executor_template_has_dynamic_matrix() -> None:
    """Executor uses fromJSON to drive the build matrix from the plan."""
    template = (TEMPLATES_DIR / "release.yml").read_text()

    assert "fromJSON(inputs.plan).matrix" in template


def test_executor_template_has_build_step() -> None:
    template = (TEMPLATES_DIR / "release.yml").read_text()

    assert "uv build" in template
    assert "jq" in template


def test_executor_template_has_granular_release_steps() -> None:
    template = (TEMPLATES_DIR / "release.yml").read_text()

    assert "fetch-unchanged" in template
    assert "publish-releases" in template
    assert "finalize" in template
