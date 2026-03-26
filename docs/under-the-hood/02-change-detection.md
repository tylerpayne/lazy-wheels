# Change Detection

How `build_plan()` discovers packages, finds baselines, diffs, and propagates
dirtiness through the dependency graph.

See [Releasing](../user-guide/02-releasing.md) and [How it works](../user-guide/09-architecture.md) for usage context.

## Source files

| Module | Key functions |
|--------|---------------|
| `pipeline.py` | `build_plan`, `discover_packages`, `find_release_tags`, `find_dev_baselines`, `detect_changes` |
| `toml.py` | `get_workspace_member_globs`, `get_uvr_config`, `get_all_dependency_strings` |
| `deps.py` | `dep_canonical_name` |
| `graph.py` | `topo_sort` |

## Discovery -- `pipeline.py:discover_packages`

1. **Read member globs.** `toml.py:get_workspace_member_globs` reads
   `[tool.uv.workspace].members` from the root `pyproject.toml` (e.g.,
   `["packages/*"]`).

2. **Expand globs.** Each pattern is resolved against the workspace root with
   `glob.glob`. Only directories containing a `pyproject.toml` are kept.

3. **First pass: collect metadata.** For each member directory, reads
   `[project].name` (canonicalized via `packaging.utils.canonicalize_name`),
   `[project].version`, and raw dependency strings from all three dependency
   locations (`[project].dependencies`, `[project].optional-dependencies.*`,
   `[dependency-groups].*`).

4. **Apply include/exclude filters.** `toml.py:get_uvr_config` reads
   `[tool.uvr.config]` from the root pyproject. If `include` is set, only those
   packages are kept. Then `exclude` removes any remaining matches.

5. **Second pass: resolve internal deps.** For each package, each raw dependency
   string is canonicalized via `deps.py:dep_canonical_name` (which parses the
   PEP 508 string with `packaging.requirements.Requirement` then
   `canonicalize_name`). If the canonical name matches a workspace package, it is
   recorded as an internal dependency.

### Data flow

```
discover_packages(root)
  -> load_pyproject(root / "pyproject.toml")
  -> get_workspace_member_globs(doc)          # ["packages/*"]
  -> glob.glob for each pattern
  -> for each member dir:
       load_pyproject(member / "pyproject.toml")
       get_project_name / get_project_version
       get_all_dependency_strings
  -> get_uvr_config(root_doc)                 # include/exclude
  -> filter packages
  -> resolve internal deps via dep_canonical_name
  -> dict[str, PackageInfo]
```

## Tag lookup

### `pipeline.py:find_release_tags`

For each package, runs `git tag --list {name}/v* --sort=-v:refname` and returns
the first tag that does **not** end in `-dev`. This is the most recent release
tag (e.g., `my-pkg/v1.2.3`).

### `pipeline.py:find_dev_baselines`

For each package, first looks for `-dev` tags via
`git tag --list {name}/v*-dev --sort=-v:refname`. If found, returns the most
recent one (e.g., `my-pkg/v1.2.4-dev`). Otherwise falls back to the release tag
for backward compatibility with repos that predate the dev-baseline convention.

The dev baseline tag is placed on the version-bump commit after each release.
This means the diff for the next release starts from the bump commit, not the
release commit -- so the version bump itself is excluded from change detection.

## Diffing -- `pipeline.py:detect_changes`

A package is marked dirty if any of these conditions hold:

1. **`rebuild_all` is True** -- all packages are dirty.
2. **No baseline tag exists** -- first release for this package.
3. **Files in the package directory changed** -- `git diff --name-only {baseline} HEAD`
   is filtered to files under `{info.path}/`.
4. **Root `pyproject.toml` changed** -- workspace-level config changes affect all
   packages.

After direct dirtiness is determined, **transitive propagation** marks dependents
dirty using BFS over a reverse dependency map:

```python
# Build reverse dependency map
reverse_deps: dict[str, list[str]] = {n: [] for n in packages}
for name, info in packages.items():
    for dep in info.deps:
        reverse_deps[dep].append(name)

# BFS propagation
queue = list(dirty)
while queue:
    node = queue.pop(0)
    for dependent in reverse_deps[node]:
        if dependent not in dirty:
            dirty.add(dependent)
            queue.append(dependent)
```

This ensures that if package C depends on B which depends on A, and A changes,
both B and C are rebuilt even if their own files are untouched.

## `build_plan()` orchestration

`pipeline.py:build_plan` ties all the above together and returns a
`(ReleasePlan, pin_changes)` tuple:

```
build_plan(rebuild_all, matrix, uvr_version, python_version)
  -> discover_packages()
  -> find_release_tags(packages)
  -> find_dev_baselines(packages)
  -> detect_changes(packages, dev_baselines, rebuild_all)
  -> split into changed / unchanged dicts
  -> strip .dev suffixes from changed versions
  -> compute published_versions for dep pinning
  -> update_dep_pins(..., write=False) for each changed package  # dry-run
  -> compute BumpPlan for each changed package (bump_patch)
  -> expand build matrix (per-package, per-runner)
  -> build publish matrix (release notes, tags, make_latest)
  -> assemble ReleasePlan
  -> return (plan, pin_changes)
```

Key detail: `build_plan` calls `update_dep_pins` with `write=False`. It only
*detects* pin changes. The caller (`cmd_release`) decides whether to prompt the
user to write them. See [Dependency pinning](03-dependency-pinning.md) for more.
