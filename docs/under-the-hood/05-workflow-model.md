# Workflow Model

The Pydantic model hierarchy that represents `.github/workflows/release.yml`.

See [Add CI hooks](../user-guide/04-hooks.md) and [How it works](../user-guide/09-architecture.md) for usage.

## Source files

| Module | Key symbols |
|--------|-------------|
| `models.py` | `ReleaseWorkflow`, `WorkflowTrigger`, `WorkflowDispatch`, `WorkflowInput`, `WorkflowJobs`, `Job`, `HookJob`, `PreBuildJob`, `BuildJob`, `PostBuildJob`, `PreReleaseJob`, `PublishJob`, `FinalizeJob`, `PostReleaseJob`, `JOB_ORDER`, `_frozen`, `_needs_validator`, `_NOOP_STEPS`, `_P` |

## Top-level model: `ReleaseWorkflow`

```python
class ReleaseWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = "Release Wheels"
    on: WorkflowTrigger = Field(default_factory=WorkflowTrigger)
    permissions: dict[str, str] = Field(default_factory=lambda: {"contents": "write"})
    jobs: WorkflowJobs = Field(default_factory=WorkflowJobs)
```

`extra="forbid"` means unknown top-level keys cause validation errors. The
`_normalize_on_key` model validator handles the PyYAML/ruamel quirk where `on:`
is parsed as boolean `True` (see [Init and validation](01-init-and-validation.md)).

## Trigger model

```
WorkflowTrigger (extra="allow")
  └── workflow_dispatch: WorkflowDispatch
        └── inputs: {"plan": WorkflowInput(type="string", required=True)}
```

`WorkflowTrigger` uses `extra="allow"` so users can add triggers like `push:` or
`schedule:` without breaking validation.

## Job hierarchy

All jobs inherit from `Job`:

```python
class Job(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    runs_on: str = Field(default="ubuntu-latest", alias="runs-on")
    if_condition: str | None = Field(default=None, alias="if")
    needs: list[str] = Field(default_factory=list)
    environment: str | None = None
    concurrency: str | dict | None = None
    timeout_minutes: int | None = Field(default=None, alias="timeout-minutes")
    env: dict[str, str] | None = None
    steps: list[dict] = Field(default_factory=list)
```

`extra="allow"` lets users add arbitrary keys (like `permissions`, `outputs`) to
any job without validation failures.

The `_drop_empty_needs` serializer removes `needs: []` from output so the YAML
is clean.

### `HookJob`

```python
class HookJob(Job):
    steps: list[dict] = Field(default_factory=lambda: list(_NOOP_STEPS))

    @model_validator(mode="after")
    def _ensure_steps(self) -> HookJob:
        if not self.steps:
            self.steps = list(_NOOP_STEPS)
        return self
```

Hook jobs default to `_NOOP_STEPS` and enforce that steps is never empty (GitHub
Actions requires at least one step per job). `_NOOP_STEPS` is:

```python
_NOOP_STEPS: list[dict] = [{"name": "Never", "run": "echo 'Never'"}]
```

### Concrete job types

| Class | Parent | Default `if` | `_needs_validator` |
|-------|--------|-------------|-------------------|
| `PreBuildJob` | `HookJob` | `!contains(plan.skip, 'pre-build')` | (none) |
| `BuildJob` | `Job` | `!contains(plan.skip, 'build')` | `pre-build` |
| `PostBuildJob` | `HookJob` | `always() && !failure() && !contains(plan.skip, 'post-build')` | `build` |
| `PreReleaseJob` | `HookJob` | `always() && !failure() && !contains(plan.skip, 'pre-release')` | `post-build` |
| `PublishJob` | `Job` | `always() && !failure() && !contains(plan.skip, 'publish')` | `pre-release` |
| `FinalizeJob` | `Job` | `always() && !failure() && !contains(plan.skip, 'finalize')` | `publish` |
| `PostReleaseJob` | `HookJob` | `always() && !failure() && !contains(plan.skip, 'post-release')` | `finalize` |

The `always() && !failure()` pattern means hook and downstream jobs run even when
earlier jobs are skipped (via the `skip` list in the plan), but stop if a
preceding job actually failed.

### `_needs_validator`

A factory that returns a Pydantic `model_validator(mode="after")`. It ensures
the `needs` list always includes required upstream jobs:

```python
def _needs_validator(*required: str):
    @model_validator(mode="after")
    def _check(self: Job) -> Job:
        for dep in required:
            if dep not in self.needs:
                self.needs.insert(0, dep)
        return self
    return _check
```

Usage on each job class:

```python
class BuildJob(Job):
    _ensure_needs = _needs_validator("pre-build")

class PostBuildJob(HookJob):
    _ensure_needs = _needs_validator("build")
```

If the user removes a `needs` entry from the YAML, validation silently adds it
back. This preserves the linear pipeline without breaking user customizations.

### `_frozen` fields

Core jobs (`BuildJob`, `PublishJob`, `FinalizeJob`) use `_frozen` to protect
fields that contain `${{ fromJSON(inputs.plan) }}` expressions. These are
annotated with `Annotated[type, _frozen(default)]`:

```python
class BuildJob(Job):
    if_condition: Annotated[str | None, _frozen(_BUILD_IF)] = Field(...)
    strategy: Annotated[dict, _frozen(_BUILD_STRATEGY)] = Field(...)
    runs_on: Annotated[str, _frozen(_BUILD_RUNS_ON)] = Field(...)
    steps: Annotated[list[dict], _frozen(_BUILD_STEPS)] = Field(...)
```

See [Init and validation](01-init-and-validation.md) for the full list and
warning behavior.

## `JOB_ORDER`

```python
JOB_ORDER: list[str] = [
    "pre-build", "build", "post-build",
    "pre-release", "publish", "finalize", "post-release",
]
```

Used by `_compute_skipped` in `cli/release.py` for `--skip-to` (skip all jobs
before a given job) and by `_print_plan` to display the pipeline in order.

## `WorkflowJobs`

Maps job names to their models, using `alias` to convert between Python
attribute names (`pre_build`) and YAML keys (`pre-build`):

```python
class WorkflowJobs(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pre_build: PreBuildJob = Field(alias="pre-build", default_factory=PreBuildJob)
    build: BuildJob = Field(default_factory=BuildJob)
    post_build: PostBuildJob = Field(alias="post-build", default_factory=PostBuildJob)
    pre_release: PreReleaseJob = Field(alias="pre-release", default_factory=PreReleaseJob)
    publish: PublishJob = Field(default_factory=PublishJob)
    finalize: FinalizeJob = Field(default_factory=FinalizeJob)
    post_release: PostReleaseJob = Field(alias="post-release", default_factory=PostReleaseJob)
```

`extra="forbid"` here means the workflow cannot contain unknown job names.

## Serialization

`ReleaseWorkflow` is serialized via `model_dump(by_alias=True, exclude_none=True)`:

- `by_alias=True`: outputs YAML-compatible keys (`runs-on`, `pre-build`).
- `exclude_none=True`: omits unset optional fields like `environment`,
  `timeout-minutes`.

The `_drop_empty_needs` model serializer on `Job` additionally removes
`needs: []` from jobs that have no dependencies.

## Shared step constants

The `_P` shorthand simplifies GitHub Actions expressions throughout the model:

```python
_P = "fromJSON(inputs.plan)"
```

This is interpolated into `if` conditions, strategy matrices, and step
configurations. For example:

```python
_BUILD_IF = f"${{{{ !contains({_P}.skip, 'build') }}}}"
# expands to: ${{ !contains(fromJSON(inputs.plan).skip, 'build') }}
```

Step constant blocks (`_BUILD_STEPS`, `_PUBLISH_STEPS`, `_FINALIZE_STEPS`) are
defined at module level and referenced by the frozen field defaults. See
[CI execution](07-ci-execution.md) for what each step does.
