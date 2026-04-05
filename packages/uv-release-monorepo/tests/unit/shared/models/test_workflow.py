"""Tests for bundled release workflow template."""

from __future__ import annotations

from uv_release_monorepo.cli.workflow.init import _load_template_yaml
from uv_release_monorepo.shared.models.workflow import ReleaseWorkflow


def _template_workflow() -> dict:
    return _load_template_yaml()


def test_template_has_name() -> None:
    doc = _template_workflow()
    assert doc["name"] == "Release Wheels"


def test_template_has_plan_input() -> None:
    doc = _template_workflow()
    inputs = doc["on"]["workflow_dispatch"]["inputs"]
    assert "plan" in inputs
    assert inputs["plan"]["required"] is True


def test_template_has_core_jobs() -> None:
    doc = _template_workflow()
    jobs = doc["jobs"]
    assert "uvr-build" in jobs
    assert "uvr-release" in jobs
    assert "uvr-bump" in jobs


def test_template_validates_against_model() -> None:
    """The bundled template passes pydantic structural validation."""
    doc = _template_workflow()
    ReleaseWorkflow.model_validate(doc)


def test_template_job_needs_chain() -> None:
    doc = _template_workflow()
    jobs = doc["jobs"]
    assert "uvr-validate" in jobs["uvr-build"]["needs"]
    assert "uvr-build" in jobs["uvr-release"]["needs"]
    assert "uvr-release" in jobs["uvr-publish"]["needs"]
    assert "uvr-publish" in jobs["uvr-bump"]["needs"]


def test_template_default_permissions() -> None:
    doc = _template_workflow()
    assert doc["permissions"] == {"contents": "write", "id-token": "write"}


def test_template_core_jobs_have_executor_steps() -> None:
    doc = _template_workflow()
    build_steps = doc["jobs"]["uvr-build"]["steps"]
    assert any("uvr jobs build" in str(s.get("run", "")) for s in build_steps)

    release_steps = doc["jobs"]["uvr-release"]["steps"]
    assert any("uvr jobs release" in str(s.get("run", "")) for s in release_steps)

    bump_steps = doc["jobs"]["uvr-bump"]["steps"]
    assert any("uvr jobs bump" in str(s.get("run", "")) for s in bump_steps)
