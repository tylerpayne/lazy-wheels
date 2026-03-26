# Release Plan

The `ReleasePlan` model is the single artifact passed from the local CLI to CI.
It encodes everything the executor needs with zero git access.

See [How it works](../guide/09-architecture.md) and [Skip jobs and reuse artifacts](../guide/06-skip-reuse.md) for usage.

## Source files

| Module | Key symbols |
|--------|-------------|
| `models.py` | `ReleasePlan`, `PackageInfo`, `BumpPlan`, `MatrixEntry`, `PublishEntry` |
| `pipeline.py` | `build_plan` (assembles the plan), `write_dep_pins`, `apply_bumps`, `execute_plan` |
| `cli/release.py` | `cmd_release` (populates skip/reuse/install fields) |

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `int` | Currently `5`. Bumped when the plan shape changes. |
| `uvr_version` | `str` | Version of uvr that created the plan. Empty string if running a `.dev` version. |
| `uvr_install` | `str` | The pip install spec for CI (e.g., `uv-release-monorepo==0.5.2` or just `uv-release-monorepo` for dev). |
| `python_version` | `str` | Python version for CI (default `"3.12"`). |
| `rebuild_all` | `bool` | Whether `--rebuild-all` was passed. |
| `changed` | `dict[str, PackageInfo]` | Packages that need rebuilding. Versions are clean (no `.dev`). |
| `unchanged` | `dict[str, PackageInfo]` | Packages reused from previous releases. |
| `release_tags` | `dict[str, str \| None]` | Most recent release tag per package, or `None`. |
| `matrix` | `list[MatrixEntry]` | Expanded build matrix -- one entry per (package, runner) pair. |
| `runners` | `list[str]` | Unique runner labels extracted from `matrix`. Drives the workflow's `strategy.matrix.runner`. |
| `bumps` | `dict[str, BumpPlan]` | Pre-computed version bumps for changed packages. |
| `publish_matrix` | `list[PublishEntry]` | One entry per changed package with release notes, tag, title, dist name. |
| `ci_publish` | `bool` | `True` when dispatched to CI (publish job creates GitHub releases). `False` for local execution. |
| `skip` | `list[str]` | Job names to skip (e.g., `["pre-build", "post-build"]`). |
| `reuse_run_id` | `str` | If non-empty, download artifacts from this workflow run instead of building. |

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
    new_version: str   # e.g., "0.1.6" (patch bump of the release version)
```

CI applies this by writing `make_dev(new_version)` (e.g., `"0.1.6.dev"`) into
`pyproject.toml`.

### `MatrixEntry`

```python
class MatrixEntry(BaseModel):
    package: str       # package name
    runner: str        # e.g., "ubuntu-latest"
    path: str          # package path
    version: str       # release version
```

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

## `skip` behavior

The `skip` list drives the `if` condition on each workflow job:

```yaml
if: ${{ !contains(fromJSON(inputs.plan).skip, 'build') }}
```

When a job name is in `skip`, its `if` evaluates to `false` and GitHub Actions
skips it. Downstream jobs with `always() && !failure()` conditions still run.

`cmd_release` auto-populates `skip` for hook jobs whose steps are still the
default `_NOOP_STEPS`:

```python
for phase in ["pre-build", "post-build", "pre-release", "post-release"]:
    job = jobs_dict.get(phase, {})
    if job.get("steps") == _NOOP_STEPS:
        skipped.add(phase)
```

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

`schema_version` is currently `5`. It is a simple integer that gets bumped when
the plan shape changes in a backward-incompatible way. There is no migration
logic -- if CI receives a plan with an unexpected schema version, it will likely
fail with a Pydantic validation error.

## Serialization

The plan is serialized as JSON via `plan.model_dump_json()` and passed as the
`plan` input to `gh workflow run release.yml -f plan=<json>`. In CI, it is
deserialized with `ReleasePlan.model_validate_json(plan_json)`. GitHub Actions
expressions access it via `${{ fromJSON(inputs.plan).field }}`.
