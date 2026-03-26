# Build Matrix

How the build matrix is expanded, how packages are grouped by runner and
topological layer, and how `uvr-steps build-all` executes builds in CI.

See [Configure build runners](../guide/03-runners.md) for usage.

## Source files

| Module | Key functions |
|--------|---------------|
| `pipeline.py` | `build_plan` (matrix expansion section) |
| `graph.py` | `topo_sort`, `topo_layers` |
| `workflow_steps.py` | `execute_build_all` |
| `models.py` | `MatrixEntry`, `BuildJob`, `_BUILD_STRATEGY` |
| `cli/release.py` | `_print_plan` (build order display) |
| `cli/_common.py` | `_read_matrix` |
| `toml.py` | `get_uvr_matrix` |

## Matrix configuration

Per-package runners are stored in `[tool.uvr.matrix]` in the root `pyproject.toml`:

```toml
[tool.uvr.matrix]
my-pkg = ["ubuntu-latest", "macos-latest"]
other-pkg = ["ubuntu-latest"]
```

`toml.py:get_uvr_matrix` parses this into `dict[str, list[str]]`. Packages not
listed default to `["ubuntu-latest"]` during matrix expansion.

## Matrix expansion in `build_plan`

`pipeline.py:build_plan` expands the matrix after change detection. Only changed
packages appear in the matrix:

```python
matrix_entries: list[MatrixEntry] = []
for name in sorted(changed_names):
    info = changed[name]
    runners = matrix.get(name, ["ubuntu-latest"])
    for runner in runners:
        matrix_entries.append(
            MatrixEntry(package=name, runner=runner, path=info.path, version=info.version)
        )
```

Each `MatrixEntry` carries the package name, runner label, path, and version.
The plan also stores `runners` -- the deduplicated list of all runner labels,
used by the workflow's `strategy.matrix.runner` expression.

## Workflow strategy

The `BuildJob` in `models.py` has a frozen strategy:

```python
_BUILD_STRATEGY = {
    "fail-fast": False,
    "matrix": {"runner": f"${{{{ {_P}.runners }}}}"},
}
```

This creates one job per unique runner label. The actual package-to-runner
mapping is resolved inside each job by `uvr-steps build-all --runner`.

## `graph.py:topo_sort`

Kahn's algorithm. Produces a flat build order where dependencies come before
dependents. Packages with equal in-degree are sorted alphabetically for
determinism.

```
Input:  {A -> [B], B -> [C], C -> []}
Output: [C, B, A]
```

Raises `RuntimeError` if a cycle is detected (processed count != total count).

## `graph.py:topo_layers`

Modified Kahn's algorithm that assigns each package a layer number instead of a
flat position:

- **Layer 0**: packages with no internal dependencies among the input set.
- **Layer N**: packages whose deepest dependency is in layer N-1.

```python
layers[dependent] = max(layers.get(dependent, 0), layers[node] + 1)
```

Layers are used for display purposes in `_print_plan` to show which packages
can build in parallel within a runner.

## Display in `_print_plan`

`cli/release.py:_print_plan` groups matrix entries by runner, then by layer:

```
  run   build
          ubuntu-latest
            layer 0
              pkg-alpha (0.1.5)
              pkg-beta (0.2.0)
            layer 1
              pkg-gamma (0.3.0)
          macos-latest
            layer 0
              pkg-alpha (0.1.5)
```

Layers are only shown when `max_layer > 0` (i.e., there are actual dependencies
between changed packages).

## `workflow_steps.py:execute_build_all`

This is the CI-side entry point. Invoked as:

```
uvr-steps build-all --plan "$UVR_PLAN" --runner 'ubuntu-latest'
```

### Algorithm

1. **Identify assigned packages.** Filters `plan.matrix` entries to those
   matching `--runner`.

2. **Collect transitive deps.** BFS from assigned packages through
   `all_packages` (union of `plan.changed` and `plan.unchanged`). This ensures
   build-time dependencies are available even if they aren't assigned to this
   runner.

3. **Split needed packages.** Needed packages in `plan.changed` are built from
   source; those in `plan.unchanged` have their wheels fetched from GitHub
   releases.

4. **Fetch unchanged wheels.** Calls `fetch_unchanged_wheels` for any unchanged
   transitive deps so `uv build --find-links dist/` can resolve them.

5. **Build in topo order.** `topo_sort(changed_to_build)` determines build
   order. For each package:
   - Strips `.dev` suffix via `rewrite_pyproject`
   - Runs `uv build {path} --out-dir dist/ --find-links dist/`

6. **Clean up non-assigned wheels.** After building, removes wheels for packages
   that were only built as transitive dependencies (not assigned to this runner).
   This prevents the upload artifact step from including wheels that belong to
   other runners.

### Data flow

```
execute_build_all(plan_json, runner)
  -> filter plan.matrix by runner -> assigned set
  -> BFS from assigned through all_packages -> needed set
  -> split needed into changed_to_build / unchanged_deps
  -> fetch_unchanged_wheels(unchanged_deps, plan.release_tags)
  -> topo_sort(changed_to_build) -> build_order
  -> for each pkg in build_order:
       rewrite_pyproject(strip .dev)
       uv build {path} --out-dir dist/ --find-links dist/
  -> remove wheels for non-assigned packages
```
