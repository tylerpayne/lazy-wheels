# Python Hooks

For deeper customization than workflow jobs allow, subclass `ReleaseHook` to run Python code at specific points in the pipeline.

## Setup

Create `uvr_hooks.py` at your workspace root:

```python
from uv_release_monorepo.shared.hooks import ReleaseHook
from uv_release_monorepo.shared.models import PlanConfig, ReleasePlan


class Hook(ReleaseHook):
    def post_plan(self, plan: ReleasePlan) -> ReleasePlan:
        # Modify the plan before it's dispatched
        return plan
```

uvr discovers this automatically by convention. For a custom path or class name:

```toml
[tool.uvr.hooks]
file = "scripts/my_hooks.py:MyHook"
```

## Available hooks

### Local (run on your machine during `uvr release`)

| Hook | Signature | Use case |
|------|-----------|----------|
| `pre_plan` | `(config: PlanConfig) -> PlanConfig` | Modify planner config before change detection |
| `post_plan` | `(plan: ReleasePlan) -> ReleasePlan` | Transform the plan before dispatch (inject extra data, modify skip list) |

### CI (run during executor phases)

| Hook | When | Use case |
|------|------|----------|
| `pre_build` / `post_build` | Before/after entire build phase | Setup/teardown |
| `pre_build_stage` / `post_build_stage` | Before/after each topo layer | Layer-level logging |
| `pre_build_package` / `post_build_package` | Before/after each package build (parallel) | Per-package metrics |
| `pre_release` / `post_release` | Before/after GitHub release creation | Custom publishing |
| `pre_bump` / `post_bump` | Before/after version bumps | Custom post-release actions |

## Example: inject custom data into the plan

```python
class Hook(ReleaseHook):
    def post_plan(self, plan: ReleasePlan) -> ReleasePlan:
        # Extra keys travel through the pipeline to CI
        plan.__dict__["deploy_env"] = "staging"
        return plan
```

Access it in workflow jobs via `fromJSON(inputs.plan).deploy_env`.

---

**Under the hood:** [Hook system internals](../under-the-hood/07-ci-execution.md)
