# Customizing the Pipeline

## Custom workflow jobs

The generated `release.yml` has five core jobs. Add your own by editing the YAML directly and wiring them via `needs`.

### Tests before build

```yaml
checks:
  runs-on: ubuntu-latest
  if: ${{ !contains(fromJSON(inputs.plan).skip, 'checks') }}
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v6
    - run: uv sync --all-packages
    - run: uv run poe check
    - run: uv run poe test

uvr-build:
  needs: [checks]
  # ... (rest unchanged)
```

### Slack notifications

```yaml
notify:
  runs-on: ubuntu-latest
  needs: [uvr-bump]
  if: ${{ always() && !failure() && !cancelled() }}
  steps:
    - name: Notify Slack
      env:
        UVR_PLAN: ${{ inputs.plan }}
      run: |
        CHANGED=$(echo "$UVR_PLAN" | jq -r '.changed | keys | join(", ")')
        curl -X POST "$SLACK_WEBHOOK" -d "{\"text\": \"Released: $CHANGED\"}"
```

### Accessing the plan

The full release plan JSON is available as <code v-pre>${{ inputs.plan }}</code>. Use `fromJSON(inputs.plan)` in expressions.

```yaml
if: fromJSON(inputs.plan).changed['my-package'] != null
env:
  VERSION: ${{ fromJSON(inputs.plan).changed['my-package'].release_version }}
```

### Tips

- Add <code v-pre>if: ${{ !contains(fromJSON(inputs.plan).skip, '&lt;job-name&gt;') }}</code> so your job can be skipped with `--skip`.
- Use `always() && !failure() && !cancelled()` for jobs after skippable upstream jobs.
- Run <code class="brand-code">uvr workflow validate</code> after editing.

## Python hooks

Create `uvr_hooks.py` at your workspace root.

```python
from uv_release import ReleaseHook, ReleasePlan


class Hook(ReleaseHook):
    def post_plan(self, plan: ReleasePlan) -> ReleasePlan:
        # Modify the plan before dispatch
        return plan
```

### Local hooks

Run on your machine during <code class="brand-code">uvr release</code>.

| Method | Receives | Returns |
|---|---|---|
| `pre_plan` | `PlanConfig` | Modified `PlanConfig` |
| `post_plan` | `ReleasePlan` | Modified `ReleasePlan` |

### CI hooks

Run during executor phases (in GitHub Actions or locally with `--where local`).

| Method | When |
|---|---|
| `pre_build` / `post_build` | Before/after the entire build phase |
| `pre_build_stage` / `post_build_stage` | Before/after each topological layer |
| `pre_build_package` / `post_build_package` | Before/after each package build |
| `pre_release` / `post_release` | Before/after GitHub release creation |
| `pre_publish` / `post_publish` | Before/after index publishing |
| `pre_bump` / `post_bump` | Before/after the version bump phase |

### Attaching custom data to the plan

The `ReleasePlan` model allows extra keys. Attach data in `post_plan` that travels through the pipeline to CI.

```python
def post_plan(self, plan: ReleasePlan) -> ReleasePlan:
    plan.deploy_env = "staging"
    return plan
```

Access it in workflow jobs via `fromJSON(inputs.plan).deploy_env`.

---

**Under the hood.** [Workflow](../under-the-hood/04-workflow.md)
