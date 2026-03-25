"""Tests for bundled templates."""

from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent / "uv_release_monorepo" / "templates"
)


def test_executor_template_has_preamble() -> None:
    template = (TEMPLATES_DIR / "release.yml.j2").read_text()

    assert "GENERATED FILE" in template
    assert "Generated with uv-release-monorepo" in template
    assert "https://github.com/tylerpayne/uv-release-monorepo" in template
    assert "uv tool install uv-release-monorepo" in template
    assert "uvr release" in template


def test_executor_template_has_plan_input() -> None:
    template = (TEMPLATES_DIR / "release.yml.j2").read_text()

    assert "plan:" in template
    assert "required: true" in template


def test_executor_template_has_uvr_version_input() -> None:
    template = (TEMPLATES_DIR / "release.yml.j2").read_text()

    assert "uvr_version" in template
    assert "uv-release-monorepo=={0}" in template
    assert "__UVR_VERSION__" not in template


def test_executor_template_has_dynamic_matrix() -> None:
    """Executor uses fromJSON to drive build and publish matrices from the plan."""
    template = (TEMPLATES_DIR / "release.yml.j2").read_text()

    assert "fromJSON(inputs.plan).runners" in template
    assert "fromJSON(inputs.plan).publish_matrix" in template


def test_executor_template_has_build_step() -> None:
    template = (TEMPLATES_DIR / "release.yml.j2").read_text()

    assert "uvr-steps build-all" in template
    assert "matrix.runner" in template


def test_executor_template_has_publish_job() -> None:
    """Publish job uses softprops/action-gh-release, not shell scripts."""
    template = (TEMPLATES_DIR / "release.yml.j2").read_text()

    assert "softprops/action-gh-release@v2" in template
    assert "matrix.tag" in template
    assert "matrix.title" in template
    assert "matrix.body" in template


def test_executor_template_has_finalize_job() -> None:
    """Finalize job calls uvr-steps finalize with just --plan."""
    template = (TEMPLATES_DIR / "release.yml.j2").read_text()

    assert "finalize:" in template
    assert "uvr-steps finalize" in template


def test_executor_template_no_shell_release_script() -> None:
    """No gh release create or jq-based release logic in the template."""
    template = (TEMPLATES_DIR / "release.yml.j2").read_text()

    assert "gh release create" not in template
    assert "mapfile" not in template
