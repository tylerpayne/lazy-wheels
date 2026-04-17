"""ValidateWorkflowIntent: check release.yml structure against template."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..types import Plan, Workspace
from ..states.templates import load_workflow_template

_REQUIRED_JOBS = {"validate", "build", "release", "publish", "bump"}


class ValidateWorkflowIntent(BaseModel):
    """Intent to validate the release workflow. Read-only."""

    model_config = ConfigDict(frozen=True)

    type: Literal["validate_workflow"] = "validate_workflow"
    workflow_dir: str = ".github/workflows"
    show_diff: bool = False

    def guard(self, workspace: Workspace) -> None:
        """Check that the workflow file exists."""
        root = Path.cwd()
        dest = root / self.workflow_dir / "release.yml"
        if not dest.exists():
            msg = (
                f"No workflow found at {self.workflow_dir}/release.yml. "
                f"Run `uvr workflow init` first."
            )
            raise ValueError(msg)

    def plan(self, workspace: Workspace) -> Plan:
        """(state, intent) -> plan. Read-only, returns validation results."""
        errors, warnings = self._validate()
        return Plan(
            validation_errors=tuple(errors),
            validation_warnings=tuple(warnings),
        )

    def _validate(self) -> tuple[list[str], list[str]]:
        """Run validation checks. Returns (errors, warnings)."""
        import yaml

        root = Path.cwd()
        dest = root / self.workflow_dir / "release.yml"
        existing_text = dest.read_text()
        existing = yaml.safe_load(existing_text)

        errors: list[str] = []
        warnings: list[str] = []

        if existing and "jobs" in existing:
            job_names = set(existing["jobs"].keys())
            missing = _REQUIRED_JOBS - job_names
            for job in sorted(missing):
                errors.append(f"Required job '{job}' is missing")
        elif existing:
            errors.append("No 'jobs' section found in release.yml")

        fresh_text = load_workflow_template()
        has_diff = fresh_text.rstrip() != existing_text.rstrip()
        if has_diff:
            warnings.append("Workflow differs from bundled template")

        return errors, warnings
