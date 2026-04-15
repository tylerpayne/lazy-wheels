# <code class="brand-code">uvr workflow</code>: A CI Template You Never Debug

<code class="brand-code">uvr</code>'s workflow YAML never changes when your repo structure changes. Add packages, change dependency graphs, modify build matrices. The YAML stays the same. All intelligence is in the [plan JSON](architecture.md), and the workflow just reads it.

```yaml
# This drives the entire build matrix.
# Works for 1 package or 100, 1 runner or 10.
strategy:
  matrix:
    runner: ${{ fromJSON(inputs.plan).build_matrix }}
```

## The `ReleaseWorkflow` model

A Pydantic model defines the expected schema for `release.yml`.

1. **Generation.** <code class="brand-code">uvr workflow init</code> instantiates `ReleaseWorkflow()` with defaults and serializes to YAML.
2. **Validation.** <code class="brand-code">uvr workflow validate</code> loads the YAML and runs all validators including frozen field checks.
3. **Documentation.** The model is the single source of truth for what the workflow should look like.

All jobs inherit from `Job` with `extra="allow"`. You can add arbitrary keys (permissions, outputs, concurrency) without breaking validation.

## Frozen fields

Core jobs contain `fromJSON(inputs.plan)` expressions that CI depends on. Changing them silently breaks the pipeline. <code class="brand-code">uvr</code> marks them **frozen**. Validation warns (but doesn't block) if they're modified.

| Job | Frozen fields |
|-----|--------------|
| `BuildJob` | `if`, `strategy`, `runs-on`, `steps` |
| `ReleaseJob` | `if`, `strategy`, `steps` |
| `BumpJob` | `if`, `steps` |

## Pipeline enforcement

Core jobs have mandatory `needs` dependencies.

```
uvr-validate → uvr-build → uvr-release → uvr-bump
```

If you remove a required `needs` entry, the `_needs_validator` silently adds it back. You can add extra entries (e.g., `needs: [uvr-build, my-test-job]`) but can't remove the required ones.

## Custom workflow jobs

Add your own jobs to `release.yml` by editing the YAML directly. `WorkflowJobs` uses `extra="allow"`, so any additional jobs pass validation.

```yaml
pre-build:
  needs: [uvr-validate]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: uv run poe check
    - run: uv run poe test
```

Custom jobs survive <code class="brand-code">uvr workflow init --upgrade</code>. The three-way merge preserves user additions.

## Python hooks

For injecting data into the plan before it reaches CI.

```python
from uv_release import ReleaseHook, ReleasePlan

class Hook(ReleaseHook):
    def post_plan(self, plan: ReleasePlan) -> ReleasePlan:
        data = plan.model_dump()
        data["deploy_env"] = "staging"
        return ReleasePlan.model_validate(data)
```

**Local hooks** run on your machine during <code class="brand-code">uvr release</code>. `pre_plan`, `post_plan`.

**CI hooks** run inside the workflow. `pre_build`, `post_build`, `pre_build_stage`, `post_build_stage`, `pre_build_package`, `post_build_package`, `pre_release`, `post_release`, `pre_publish`, `post_publish`, `pre_bump`, `post_bump`.

## Init, validate, and upgrade

### <code class="brand-code">uvr workflow init</code>

Generates `release.yml` from defaults. Checks that the CWD is a git repo with `[tool.uv.workspace].members`. Refuses to overwrite without `--force`.

### <code class="brand-code">uvr workflow validate</code>

Validates the existing YAML against the model. Reports frozen field warnings and errors. Never modifies the file.

### <code class="brand-code">uvr workflow init --upgrade</code>

Performs a three-way merge between the merge base (defaults from the <code class="brand-code">uvr</code> version that generated the file), the current file (your customized version), and the new defaults (from the current <code class="brand-code">uvr</code> version).

Your customizations are preserved. Conflicts open in your editor. Use `--base-only` to inspect merge bases without merging.
