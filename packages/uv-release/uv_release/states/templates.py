"""Shared template loaders for workflow and skill intents."""

from __future__ import annotations

from importlib.resources import files

_WORKFLOW_TEMPLATE_PATH = files("uv_release").joinpath("templates/release/release.yml")


def load_workflow_template() -> str:
    """Load the bundled release.yml template."""
    return _WORKFLOW_TEMPLATE_PATH.read_text(encoding="utf-8")
