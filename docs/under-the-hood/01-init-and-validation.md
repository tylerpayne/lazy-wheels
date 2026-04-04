# Init and Validation

How `uvr workflow init` scaffolds the workflow and `uvr workflow validate` checks it.

See [Set up your first release](../user-guide/01-setup.md) for usage.

## Source files

| Module | Key functions |
|--------|---------------|
| `cli/init.py` | `cmd_init`, `cmd_validate` |
| `models.py` | `ReleaseWorkflow`, all job classes, `_frozen`, `_NOOP_STEPS` |
| `cli/_yaml.py` | `_load_yaml`, `_write_yaml` |

## `uvr workflow init` -- `cli/init.py:cmd_init`

1. **Sanity checks.** Verifies the CWD is a git repo and contains a `pyproject.toml`
   with `[tool.uv.workspace].members` defined. Exits with a descriptive error if any
   check fails.

2. **Generates defaults.** Instantiates `ReleaseWorkflow()` with zero arguments. Every
   field has a default, so this produces a complete workflow definition: name, `on:`,
   permissions, and all seven jobs with their default steps and `needs` chains.

3. **Serializes to YAML.** Calls `model_dump(by_alias=True, exclude_none=True)` to get
   a dict using YAML-friendly keys (e.g., `runs-on` instead of `runs_on`), then writes
   it through `_write_yaml` (ruamel.yaml, preserves ordering).

4. **Respects `--force`.** If `release.yml` already exists and `--force` is not set,
   `cmd_init` exits with an error pointing the user to `uvr workflow validate`.

### Data flow

```
cmd_init
  -> ReleaseWorkflow()           # full default model
  -> .model_dump(by_alias=True)  # dict with YAML keys
  -> _write_yaml(dest, dict)     # ruamel.yaml -> .github/workflows/release.yml
```

## `uvr workflow validate` -- `cli/init.py:cmd_validate`

1. **Loads existing YAML.** Reads `.github/workflows/release.yml` with `_load_yaml`.

2. **Validates against model.** Passes the raw dict to
   `ReleaseWorkflow.model_validate(existing)`. Pydantic runs all field validators
   including `_frozen` checks on core job fields.

3. **Collects warnings.** Uses `warnings.catch_warnings(record=True)` to capture
   `_frozen` warnings without crashing. If the model is valid but has warnings,
   `cmd_validate` prints them. If `model_validate` raises `ValidationError`, it prints
   the errors and exits with code 1.

### What `_frozen` warns on

`_frozen(default)` is an `AfterValidator` that compares the deserialized value against
a known default. If they differ, it emits a `UserWarning`:

```python
def _frozen(default: Any) -> AfterValidator:
    def _check(v: Any) -> Any:
        if v != default:
            warnings.warn(
                "core job field was modified from its default -- "
                "this may break the release pipeline",
                UserWarning,
            )
        return v
    return AfterValidator(_check)
```

Fields protected by `_frozen`:

| Job | Field | Default constant |
|-----|-------|------------------|
| `BuildJob` | `if_condition` | `_BUILD_IF` |
| `BuildJob` | `strategy` | `_BUILD_STRATEGY` |
| `BuildJob` | `runs_on` | `_BUILD_RUNS_ON` (<code v-pre>${{ matrix.runner }}</code>) |
| `BuildJob` | `steps` | `_BUILD_STEPS` |
| `ReleaseJob` | `if_condition` | `_RELEASE_IF` |
| `ReleaseJob` | `strategy` | `_RELEASE_STRATEGY` |
| `ReleaseJob` | `steps` | `_RELEASE_STEPS` |
| `BumpJob` | `if_condition` | `_BUMP_IF` |
| `BumpJob` | `steps` | `_BUMP_STEPS` |

These fields are "frozen" because their values contain `fromJSON(inputs.plan)` expressions
that the CI executor depends on. Changing them will silently break the pipeline. The
warning is non-fatal because `uvr workflow validate` is advisory -- it tells the user what they
broke without blocking them.

### The `_normalize_on_key` model validator

PyYAML and ruamel parse the YAML key `on:` as boolean `True`. `ReleaseWorkflow` has a
`mode="before"` model validator that converts `{True: ...}` to `{"on": ...}` before
Pydantic sees it:

```python
@model_validator(mode="before")
@classmethod
def _normalize_on_key(cls, data: Any) -> Any:
    if isinstance(data, dict) and True in data:
        data["on"] = data.pop(True)
    return data
```
