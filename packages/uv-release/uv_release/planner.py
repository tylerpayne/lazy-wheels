"""Orchestrator: parse state, apply intent, return plan."""

from __future__ import annotations

from .states.hooks import parse_hooks
from .states.workspace import parse_workspace
from .types import Hooks, Intent, Plan, PlanMetadata, Unset, UNSET, Workspace


def compute_plan(
    intent: Intent,
    *,
    workspace: Workspace | None = None,
    hooks: Hooks | None | Unset = UNSET,
) -> Plan:
    """Single entry point. CLI calls this.

    Accepts optional workspace and hooks. When omitted,
    workspace is parsed from disk and hooks are loaded from pyproject.toml.
    """
    if workspace is None:
        workspace = parse_workspace()
    if isinstance(hooks, Unset):
        hooks = parse_hooks()

    if hooks:
        intent = hooks.pre_plan(workspace, intent)

    intent.guard(workspace)
    result = intent.plan(workspace)

    if hooks:
        result = hooks.post_plan(workspace, intent, result)

    metadata = PlanMetadata(workspace=workspace)
    return result.model_copy(update={"metadata": metadata})
