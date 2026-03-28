"""Tests for ReleaseWorkflow model serialization."""

from __future__ import annotations

from uv_release_monorepo.shared.models.workflow import ReleaseWorkflow


def _default_workflow() -> dict:
    return ReleaseWorkflow().model_dump(by_alias=True, exclude_none=True)


def test_workflow_has_name() -> None:
    doc = _default_workflow()
    assert doc["name"] == "Release Wheels"


def test_workflow_has_plan_input() -> None:
    doc = _default_workflow()
    inputs = doc["on"]["workflow_dispatch"]["inputs"]
    assert "plan" in inputs
    assert inputs["plan"]["required"] is True


def test_workflow_has_core_jobs() -> None:
    doc = _default_workflow()
    jobs = doc["jobs"]
    assert "build" in jobs
    assert "release" in jobs
    assert "finalize" in jobs


def test_workflow_job_needs_chain() -> None:
    doc = _default_workflow()
    jobs = doc["jobs"]
    assert jobs["release"]["needs"] == ["build"]
    assert jobs["finalize"]["needs"] == ["release"]


def test_workflow_default_permissions() -> None:
    doc = _default_workflow()
    assert doc["permissions"] == {"contents": "write"}


def test_workflow_core_jobs_have_executor_steps() -> None:
    doc = _default_workflow()
    build_steps = doc["jobs"]["build"]["steps"]
    assert any("uvr build" in str(s.get("run", "")) for s in build_steps)

    release_steps = doc["jobs"]["release"]["steps"]
    assert any(
        s.get("uses", "").startswith("softprops/action-gh-release")
        for s in release_steps
    )

    finalize_steps = doc["jobs"]["finalize"]["steps"]
    assert any("uvr finalize" in str(s.get("run", "")) for s in finalize_steps)
