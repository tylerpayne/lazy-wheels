# Build Matrix

How the build matrix is expanded, how packages are grouped by runner and
topological layer, and how `uvr jobs build` executes builds in CI.

See [Configure build runners](../user-guide/03-runners.md) for usage.

## Source files

| Module | Key symbols |
|--------|-------------|
| `planner/_planner.py` | `ReleasePlanner._generate_build_commands`, `ReleasePlanner._expand_matrix`, `ReleasePlanner._collect_deps` |
| `planner/_graph.py` | `topo_sort`, `topo_layers` |
| `executor.py` | `ReleaseExecutor.build`, `ReleaseExecutor._run_stage` |
| `models/plan.py` | `ChangedPackage`, `BuildStage`, `ReleasePlan.build_matrix` (computed field) |
| `models/workflow.py` | `BuildJob`, `_BUILD_STRATEGY` |
| `cli/release.py` | `_print_plan` (build order display) |
| `cli/_common.py` | `_read_matrix` |
| `config.py` | `get_matrix` |

## Matrix configuration

Per-package runners are stored in `[tool.uvr.matrix]` in the root `pyproject.toml`.
Each runner is a list of labels (for composite runner selection):

```toml
[tool.uvr.matrix]
my-pkg = [["ubuntu-latest"], ["macos-latest"]]
other-pkg = [["ubuntu-latest"]]
```

`config.py:get_matrix` parses this into `dict[str, list[list[str]]]`. Packages
not listed default to `[["ubuntu-latest"]]` during matrix expansion.

## Matrix expansion in `ReleasePlanner`

`ReleasePlanner._expand_matrix` assigns runners to each `ChangedPackage` after
change detection. Only changed packages appear in the matrix:

```python
for name in sorted(changed_names):
    runners = self.config.matrix.get(name, [["ubuntu-latest"]])
    changed[name].runners = runners
```

Each `ChangedPackage` stores its `runners` list. The plan's `build_matrix`
computed field deduplicates all runner label lists across changed packages,
producing the list used by the workflow's `strategy.matrix.runner` expression.

## Workflow strategy

The `BuildJob` in `models/workflow.py` has a frozen strategy:

```python
_BUILD_STRATEGY = {
    "fail-fast": False,
    "matrix": {"runner": f"${{{{ {_P}.runners }}}}"},
}
```

This creates one job per unique runner label list. The actual package-to-runner
mapping is resolved inside each job by `uvr jobs build --plan ... --runner ...`.

## `planner/_graph.py:topo_sort`

Kahn's algorithm. Produces a flat build order where dependencies come before
dependents. Packages with equal in-degree are sorted alphabetically for
determinism.

```
Input:  {A -> [B], B -> [C], C -> []}
Output: [C, B, A]
```

Raises `RuntimeError` if a cycle is detected (processed count != total count).

## `planner/_graph.py:topo_layers`

Modified Kahn's algorithm that assigns each package a layer number instead of a
flat position:

- **Layer 0**: packages with no internal dependencies among the input set.
- **Layer N**: packages whose deepest dependency is in layer N-1.

```python
layers[dependent] = max(layers.get(dependent, 0), layers[node] + 1)
```

Layers drive parallel execution in `ReleaseExecutor._run_stage()` -- packages
within the same layer have no interdependencies and build concurrently.

## Display in `_print_plan`

`cli/release.py:_print_plan` groups matrix entries by runner, then by layer:

```
  run   build
          [ubuntu-latest]
            layer 0
              pkg-alpha (0.1.5)
              pkg-beta (0.2.0)
            layer 1
              pkg-gamma (0.3.0)
          [macos-latest]
            layer 0
              pkg-alpha (0.1.5)
```

Layers are only shown when `max_layer > 0` (i.e., there are actual dependencies
between changed packages).

## Pre-computed build commands

Build commands are generated at plan time by
`ReleasePlanner._generate_build_commands()` and stored in
`plan.build_commands` -- a `dict[str, list[BuildStage]]` keyed by
JSON-serialized runner label list.

### Algorithm

For each runner:

1. **Identify assigned packages.** Filters `matrix_entries` to those matching
   the runner.

2. **Collect transitive deps.** BFS from assigned packages through
   `all_packages` (union of `changed` and `unchanged`). This ensures build-time
   dependencies are available even if they aren't assigned to this runner.

3. **Split needed packages.** Needed packages in `changed` are built from
   source; those in `unchanged` have their wheels fetched from GitHub releases.

4. **Stage 0 -- setup.** Creates `mkdir -p dist` and `gh release download`
   commands for each unchanged transitive dep. Stored as a `BuildStage` with
   key `__setup__`.

5. **Build stages -- one per topo layer.** Calls `topo_layers(changed_to_build)`
   to assign each package a layer. For each layer, creates a `BuildStage` where
   each package maps to two commands:
   - `uv version {release_ver} --directory {path}` (strip `.dev` suffix)
   - `uv build {path} --out-dir dist/ --find-links dist/`

6. **Cleanup stage.** Removes wheels for packages that were only built as
   transitive dependencies (not assigned to this runner). Stored as a
   `BuildStage` with key `__cleanup__`.

### Data flow

```
_generate_build_commands(changed, unchanged, release_tags)
  for each runner:
    -> filter changed packages by runner -> assigned set
    -> BFS from assigned through all_packages -> needed set
    -> split needed into changed_to_build / unchanged_deps
    -> Stage 0: mkdir dist + gh release download for unchanged_deps
    -> topo_layers(changed_to_build) -> layer assignments
    -> Stage 1..N: one BuildStage per layer, each pkg gets:
         uv version {release_ver} --directory {path}
         uv build {path} --out-dir dist/ --find-links dist/
    -> Cleanup stage: find dist -name "{pkg}-*.whl" -delete for non-assigned
```

## CI execution: `ReleaseExecutor.build()`

Invoked by the workflow as:

```
uvr jobs build --plan "$UVR_PLAN" --runner '${{ toJSON(matrix.runner) }}'
```

`ReleaseExecutor.build(runner=...)` looks up the `BuildStage` list for the
given runner from `plan.build_commands` and iterates each stage sequentially.

### `_run_stage()` -- parallel package builds

Each `BuildStage` has a `commands: dict[str, list[PlanCommand]]` mapping
package names (or `__setup__`/`__cleanup__`) to command sequences.

- **Single-key stages** (setup, cleanup, or single-package layers): commands
  run sequentially with no thread overhead.

- **Multi-key stages** (layers with multiple packages): a `ThreadPoolExecutor`
  with one worker per package runs all packages concurrently. Each package's
  commands run sequentially within its thread. If any package fails, the stage
  collects all failures and exits with code 1.

```python
with ThreadPoolExecutor(max_workers=len(stage.commands)) as pool:
    futures = {
        pool.submit(_run_pkg, pkg, cmds): pkg
        for pkg, cmds in stage.commands.items()
    }
    for future in as_completed(futures):
        failed = future.result()
        if failed is not None:
            failures.append(failed)
```

### Full execution flow

```
ReleaseExecutor.build(runner='["ubuntu-latest"]')
  -> key = json.dumps(["ubuntu-latest"])
  -> stages = plan.build_commands[key]
  -> for stage in stages:
       _run_stage(stage)
         -> if single key: run commands sequentially
         -> if multiple keys: ThreadPoolExecutor, one thread per package
```
