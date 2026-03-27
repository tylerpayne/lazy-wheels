# Release Plan

The `ReleasePlan` model is the single artifact passed from the local CLI to CI.
It encodes everything the executor needs with zero git access.

See [How it works](../user-guide/09-architecture.md) and [Skip jobs and reuse artifacts](../user-guide/06-skip-reuse.md) for usage.

## Source files

| Module | Key symbols |
|--------|-------------|
| `models.py` | `ReleasePlan`, `PackageInfo`, `BumpPlan`, `MatrixEntry`, `PublishEntry`, `PlanCommand`, `BuildStage`, `PlanConfig` |
| `plan.py` | `ReleasePlanner`, `build_plan` (thin wrapper), `write_dep_pins` |
| `cli/release.py` | `cmd_release` (populates skip/reuse/install fields) |

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `int` | Currently `7`. Bumped when the plan shape changes. |
| `uvr_version` | `str` | Version of uvr that created the plan. Empty string if running a `.dev` version. |
| `uvr_install` | `str` | The pip install spec for CI (e.g., `uv-release-monorepo==0.5.2` or just `uv-release-monorepo` for dev). |
| `python_version` | `str` | Python version for CI (default `"3.12"`). |
| `release_type` | `str` | One of `"final"`, `"dev"`, `"pre"`, `"post"`. Defaults to `"final"`. |
| `rebuild_all` | `bool` | Whether `--rebuild-all` was passed. |
| `changed` | `dict[str, PackageInfo]` | Packages that need rebuilding. Versions are clean (no `.dev`) for final releases. |
| `unchanged` | `dict[str, PackageInfo]` | Packages reused from previous releases. |
| `current_versions` | `dict[str, str]` | Original pyproject.toml versions for changed packages before transformation (used for display). |
| `release_tags` | `dict[str, str \| None]` | Most recent release tag per package, or `None`. |
| `matrix` | `list[MatrixEntry]` | Expanded build matrix -- one entry per (package, runner) pair. |
| `runners` | `list[list[str]]` | Unique runner label lists extracted from `matrix`. Each element is a list of labels (e.g., `["ubuntu-latest"]` or `["self-hosted", "linux"]`). Drives the workflow's `strategy.matrix.runner`. |
| `bumps` | `dict[str, BumpPlan]` | Pre-computed version bumps for changed packages. |
| `publish_matrix` | `list[PublishEntry]` | One entry per changed package with release notes, tag, title, dist name. |
| `ci_publish` | `bool` | `True` when dispatched to CI (publish job creates GitHub releases). `False` for local execution. |
| `skip` | `list[str]` | Job names to skip (e.g., `["build"]`). |
| `reuse_run_id` | `str` | If non-empty, download artifacts from this workflow run instead of building. |
| `build_commands` | `dict[str, list[BuildStage]]` | Pre-computed build command stages keyed by runner (JSON-serialized runner list). See below. |
| `publish_commands` | `list[PlanCommand]` | Pre-computed publish commands (local execution only; empty for CI). |
| `finalize_commands` | `list[PlanCommand]` | Pre-computed finalize commands (tag, bump, commit, push). |

## Sub-models

### `PackageInfo`

```python
class PackageInfo(BaseModel):
    path: str          # relative path, e.g., "packages/my-pkg"
    version: str       # clean release version, e.g., "0.1.5"
    deps: list[str]    # internal dependency names
```

### `BumpPlan`

```python
class BumpPlan(BaseModel):
    new_version: str   # e.g., "0.1.6.dev0" (patch bump + .dev0 suffix)
```

The bump depends on `release_type`:

- After final `1.0.1`: `1.0.2.dev0`
- After dev `1.0.1.dev2`: `1.0.1.dev3`
- After pre `1.0.1a0`: `1.0.1a1.dev0`
- After post `1.0.0.post0`: `1.0.0.post1.dev0`

### `MatrixEntry`

```python
class MatrixEntry(BaseModel):
    package: str          # package name
    runner: list[str]     # e.g., ["ubuntu-latest"] or ["self-hosted", "linux"]
    path: str             # package path
    version: str          # release version
```

`runner` is a list of labels, not a single string. This supports GitHub Actions
runners that require multiple labels (e.g., `[self-hosted, linux, arm64]`).

### `PublishEntry`

```python
class PublishEntry(BaseModel):
    package: str
    version: str       # e.g., "0.1.5"
    tag: str           # e.g., "my-pkg/v0.1.5"
    title: str         # e.g., "my-pkg 0.1.5"
    body: str          # markdown release notes
    make_latest: bool  # True if this is the "latest" package per [tool.uvr.config]
    dist_name: str     # e.g., "my_pkg" (underscored, for wheel glob matching)
```

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
    pre_kind: str = ""
```

Internal configuration passed to `ReleasePlanner`. Uses `dataclass` (not
`BaseModel`) because it is never serialized.

## `skip` behavior

The `skip` list drives the `if` condition on each workflow job:

```yaml
if: ${{ !contains(fromJSON(inputs.plan).skip, 'build') }}
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

When non-empty, the publish job's `download-artifact` step uses it as the
`run-id`:

```yaml
run-id: ${{ fromJSON(inputs.plan).reuse_run_id != '' && fromJSON(inputs.plan).reuse_run_id || github.run_id }}
```

This lets users skip the build job and pull wheels from a previous successful
run. Requires `build` to be in `skip`.

## `uvr_install` computation

`cmd_release` sets this field based on the current uvr version:

- **Released version** (e.g., `0.5.2`): `uvr_install = "uv-release-monorepo==0.5.2"`
- **Dev version** (e.g., `0.5.3.dev0`): `uvr_install = "uv-release-monorepo"`
  (unpinned, since .dev versions are not on PyPI)

This value is used in the CI setup step to install the correct version of uvr.

## Schema versioning

`schema_version` is currently `7`. It is a simple integer that gets bumped when
the plan shape changes in a backward-incompatible way. There is no migration
logic -- if CI receives a plan with an unexpected schema version, it will likely
fail with a Pydantic validation error.

## Serialization

The plan is serialized as JSON via `plan.model_dump_json()` and passed as the
`plan` input to `gh workflow run release.yml -f plan=<json>`. In CI, it is
deserialized with `ReleasePlan.model_validate_json(plan_json)`. GitHub Actions
expressions access it via `${{ fromJSON(inputs.plan).field }}`.
