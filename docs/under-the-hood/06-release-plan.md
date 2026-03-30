# Release Plan

The `ReleasePlan` model is the single artifact passed from the local CLI to CI.
It encodes everything the executor needs with zero git access.

See [How it works](../user-guide/09-architecture.md) and [Skip jobs and reuse artifacts](../user-guide/06-skip-reuse.md) for usage.

## Source files

| Module | Key symbols |
|--------|-------------|
| `models/plan.py` | `ReleasePlan`, `PackageInfo`, `ChangedPackage`, `PlanCommand`, `BuildStage`, `PlanConfig` |
| `planner/_planner.py` | `ReleasePlanner`, `build_plan` (thin wrapper), `write_dep_pins` |
| `cli/release.py` | `cmd_release` (populates skip/reuse/install fields) |

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `int` | Currently `9`. Bumped when the plan shape changes. |
| `uvr_version` | `str` | Version of uvr that created the plan. Empty string if running a `.dev` version. |
| `uvr_install` | `str` | The pip install spec for CI (e.g., `uv-release-monorepo==0.5.2` or just `uv-release-monorepo` for dev). |
| `python_version` | `str` | Python version for CI (default `"3.12"`). |
| `release_type` | `str` | One of `"final"`, `"dev"`. Defaults to `"final"`. Release type is auto-detected from the version. |
| `rebuild_all` | `bool` | Whether `--rebuild-all` was passed. |
| `changed` | `dict[str, ChangedPackage]` | Packages that need rebuilding. `ChangedPackage` extends `PackageInfo` with version lifecycle info and runners. |
| `unchanged` | `dict[str, PackageInfo]` | Packages reused from previous releases. |
| `ci_publish` | `bool` | `True` when dispatched to CI (release job creates GitHub releases). `False` for local execution. |
| `skip` | `list[str]` | Job names to skip (e.g., `["uvr-build"]`). |
| `reuse_run_id` | `str` | If non-empty, download artifacts from this workflow run instead of building. |
| `build_commands` | `dict[RunnerKey, list[BuildStage]]` | Pre-computed build command stages keyed by runner (JSON-serialized runner list). See below. |
| `release_commands` | `list[PlanCommand]` | Pre-computed release commands (local execution only; empty for CI). |
| `finalize_commands` | `list[PlanCommand]` | Pre-computed finalize commands (tag, bump, commit, push). |
| `build_matrix` | `list[list[str]]` | **Computed field.** Unique runner label sets across all changed packages. Drives the workflow's `strategy.matrix.runner`. |
| `release_matrix` | `list[dict[str, Any]]` | **Computed field.** One entry per changed package with tag, title, body, dist name, make_latest. Drives the release job's `strategy.matrix.include`. |

## Sub-models

### `PackageInfo`

```python
class PackageInfo(BaseModel):
    path: str          # relative path, e.g., "packages/my-pkg"
    version: str       # clean release version, e.g., "0.1.5"
    deps: list[str]    # internal dependency names
```

### `ChangedPackage`

Extends `PackageInfo` with version lifecycle and runner configuration:

```python
class ChangedPackage(PackageInfo):
    current_version: str        # version in pyproject.toml before changes
    release_version: str        # version that will be published
    next_version: str           # post-release dev version (e.g., "0.1.6.dev0")
    last_release_tag: str | None  # most recent GitHub release tag, or None
    release_notes: str          # markdown release notes
    make_latest: bool           # True if this release should be marked "Latest"
    runners: list[list[str]]    # runner label sets for build matrix
```

The next version is auto-detected from the release version:

- After stable `1.0.1`: `1.0.2.dev0`
- After dev `1.0.1.dev2`: `1.0.1.dev3`
- After pre-release `1.0.1a0`: `1.0.1a1.dev0`
- After post-release `1.0.0.post0`: `1.0.0.post1.dev0`

### `PlanCommand`

```python
class PlanCommand(BaseModel):
    args: list[str]    # command and arguments, e.g., ["git", "tag", "pkg/v1.0.0"]
    label: str         # human-readable description
    check: bool        # if True, abort on non-zero exit
```

### `BuildStage`

```python
class BuildStage(BaseModel):
    commands: dict[str, list[PlanCommand]]
```

A group of per-package command sequences that execute concurrently. Stages run
sequentially (stage 0 completes before stage 1 starts). Within a stage, each
key's commands run in a separate thread. Keys are package names, or the special
values `__setup__` (mkdir + fetch unchanged wheels) and `__cleanup__` (remove
transitive dep wheels not assigned to this runner).

### `PlanConfig`

```python
@dataclass
class PlanConfig:
    rebuild_all: bool
    matrix: dict[str, list[list[str]]]
    uvr_version: str
    python_version: str = "3.12"
    ci_publish: bool = True
    release_type: str = "final"
```

Internal configuration passed to `ReleasePlanner`. Uses `dataclass` (not
`BaseModel`) because it is never serialized.

## `skip` behavior

The `skip` list drives the `if` condition on each workflow job:

```yaml
if: ${{ !contains(fromJSON(inputs.plan).skip, 'uvr-build') }}
```

When a job name is in `skip`, its `if` evaluates to `false` and GitHub Actions
skips it. Downstream jobs with `always() && !failure()` conditions still run.

`cmd_release` populates `skip` from two CLI flags:

- `--skip <job>`: adds the named job to the skip set.
- `--skip-to <job>`: adds all jobs before the named job (per `JOB_ORDER`) to the
  skip set.

There is no automatic skip logic for hook jobs. Since hook jobs are not modeled
(they live as extra fields on `WorkflowJobs`), they are only skipped when
explicitly requested via `--skip`.

## `reuse_run_id` behavior

When non-empty, the release job's `download-artifact` step uses it as the
`run-id`:

```yaml
run-id: ${{ fromJSON(inputs.plan).reuse_run_id != '' && fromJSON(inputs.plan).reuse_run_id || github.run_id }}
```

This lets users skip the build job and pull wheels from a previous successful
run. Requires `uvr-build` to be in `skip`.

## `uvr_install` computation

`cmd_release` sets this field based on the current uvr version:

- **Released version** (e.g., `0.5.2`): `uvr_install = "uv-release-monorepo==0.5.2"`
- **Dev version** (e.g., `0.5.3.dev0`): `uvr_install = "uv-release-monorepo"`
  (unpinned, since .dev versions are not on PyPI)

This value is used in the CI setup step to install the correct version of uvr.

## Schema versioning

`schema_version` is currently `9`. It is a simple integer that gets bumped when
the plan shape changes in a backward-incompatible way. There is no migration
logic -- if CI receives a plan with an unexpected schema version, it will likely
fail with a Pydantic validation error.

## Serialization

The plan is serialized as JSON via `plan.model_dump_json()` and passed as the
`plan` input to `gh workflow run release.yml -f plan=<json>`. In CI, it is
deserialized with `ReleasePlan.model_validate_json(plan_json)`. GitHub Actions
expressions access it via `${{ fromJSON(inputs.plan).field }}`.
