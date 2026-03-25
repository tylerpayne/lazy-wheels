"""Tests for ReleaseWorkflow model serialization (replaces template tests)."""

from __future__ import annotations

from uv_release_monorepo.models import ReleaseWorkflow


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


def test_workflow_has_all_jobs() -> None:
    doc = _default_workflow()
    jobs = doc["jobs"]
    assert "pre-build" in jobs
    assert "build" in jobs
    assert "post-build" in jobs
    assert "pre-release" in jobs
    assert "publish" in jobs
    assert "finalize" in jobs
    assert "post-release" in jobs


def test_workflow_job_needs_chain() -> None:
    doc = _default_workflow()
    jobs = doc["jobs"]
    assert jobs["build"]["needs"] == ["pre-build"]
    assert jobs["post-build"]["needs"] == ["build"]
    assert jobs["pre-release"]["needs"] == ["post-build"]
    assert jobs["publish"]["needs"] == ["pre-release"]
    assert jobs["finalize"]["needs"] == ["publish"]
    assert jobs["post-release"]["needs"] == ["finalize"]


def test_workflow_pre_build_has_no_needs() -> None:
    doc = _default_workflow()
    assert "needs" not in doc["jobs"]["pre-build"]


def test_workflow_default_permissions() -> None:
    doc = _default_workflow()
    assert doc["permissions"] == {"contents": "write"}


def test_workflow_hook_jobs_have_noop_steps() -> None:
    doc = _default_workflow()
    for phase in ("pre-build", "post-build", "pre-release", "post-release"):
        steps = doc["jobs"][phase]["steps"]
        assert len(steps) >= 1
        assert steps[0]["name"] == "Never"


def test_workflow_core_jobs_have_executor_steps() -> None:
    doc = _default_workflow()
    build_steps = doc["jobs"]["build"]["steps"]
    assert any("uvr-steps build-all" in str(s.get("run", "")) for s in build_steps)

    publish_steps = doc["jobs"]["publish"]["steps"]
    assert any(
        s.get("uses", "").startswith("softprops/action-gh-release")
        for s in publish_steps
    )

    finalize_steps = doc["jobs"]["finalize"]["steps"]
    assert any("uvr-steps finalize" in str(s.get("run", "")) for s in finalize_steps)
