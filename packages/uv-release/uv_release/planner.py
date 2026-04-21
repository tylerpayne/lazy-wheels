"""Orchestrator: parse state, resolve dependencies, apply intent, return plan."""

from __future__ import annotations

from typing import Any, get_type_hints

from .git import GitRepo
from .states.base import State
from .states.hooks import parse_hooks
from .states.uvr_state import UvrState
from .states.workspace import Workspace
from .types import (
    Hooks,
    Plan,
    PlanMetadata,
    PlanParams,
    Unset,
    UNSET,
)


def compute_plan(
    intent: Any,  # Intent protocol; Any because ty cannot express variable kwargs
    *,
    params: PlanParams | None = None,
    workspace: Workspace | None = None,
    uvr_state: UvrState | None = None,
    hooks: Hooks | None | Unset = UNSET,
) -> Plan:
    """Single entry point. CLI calls this.

    Resolves each intent's declared state dependencies by inspecting type
    hints. State types with a parse() classmethod are resolved recursively.
    PlanParams and pre-resolved Workspace are seeded into the cache.
    """
    if params is None:
        params = PlanParams()
    if workspace is None:
        workspace = Workspace.parse()
    if uvr_state is None:
        uvr_state = UvrState.parse()
    if isinstance(hooks, Unset):
        hooks = parse_hooks()

    if hooks:
        intent = hooks.pre_plan(workspace, intent)

    cache: dict[type, object] = {
        PlanParams: params,
        Workspace: workspace,
        UvrState: uvr_state,
        GitRepo: GitRepo(),
    }

    guard_state = _resolve_state(intent, "guard", cache)
    intent.guard(**guard_state)

    plan_state = _resolve_state(intent, "plan", cache)
    result = intent.plan(**plan_state)

    if hooks:
        result = hooks.post_plan(workspace, intent, result)

    from .states.workflow import WorkflowState

    metadata = PlanMetadata(
        workspace=workspace,
        uvr_state=uvr_state,
        workflow_state=cache.get(WorkflowState),
    )
    return result.model_copy(update={"metadata": metadata})


def _resolve_type(state_type: type, cache: dict[type, object]) -> object:
    """Recursively resolve a type and its parse() dependencies."""
    if state_type in cache:
        return cache[state_type]

    parse_method = getattr(state_type, "parse", None)
    if parse_method is None:
        msg = (
            f"Cannot resolve {state_type.__name__}: no parse() method and not in cache"
        )
        raise TypeError(msg)

    hints = get_type_hints(parse_method)
    kwargs: dict[str, object] = {}
    for name, dep_type in hints.items():
        if name in ("cls", "return"):
            continue
        kwargs[name] = _resolve_type(dep_type, cache)

    result = parse_method(**kwargs)
    cache[state_type] = result
    return result


def _resolve_state(
    intent: Any,
    method_name: str,
    cache: dict[type, object],
) -> dict[str, object]:
    """Inspect an intent method's type hints and resolve declared deps."""
    method = getattr(intent, method_name)
    try:
        hints = get_type_hints(method)
    except Exception:
        hints = {}

    needed: dict[str, type] = {}
    for param_name, param_type in hints.items():
        if param_name in ("self", "return"):
            continue
        if isinstance(param_type, type) and (
            issubclass(param_type, State) or param_type in cache
        ):
            needed[param_name] = param_type

    for state_type in needed.values():
        _resolve_type(state_type, cache)

    return {name: cache[state_type] for name, state_type in needed.items()}
