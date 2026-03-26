# Dependency Pinning

How internal dependency constraints are computed and written before a release.

See [How it works](../guide/09-architecture.md) for the user-facing explanation.

## Source files

| Module | Key functions |
|--------|---------------|
| `deps.py` | `dep_canonical_name`, `pin_dep`, `rewrite_pyproject`, `update_dep_pins`, `_pin_dep_list` |
| `pipeline.py` | `build_plan`, `write_dep_pins`, `bump_versions`, `collect_published_state` |
| `cli/release.py` | `cmd_release` (write-prompt flow) |

## Why pins exist

When package B depends on package A, the published wheel for B must declare a
minimum version of A that is actually available. If A was released at `1.2.3` and
B still says `A>=1.0.0`, that works. But if B's code uses features added in
`1.2.3`, the constraint is wrong. uvr pins B's dependency to `A>=1.2.3` -- the
version of A that was published in the same release cycle (or the most recent
release for unchanged packages).

## Published version computation

`pipeline.py:build_plan` computes a `published_versions` dict for all packages:

- **Changed packages**: publish at their current version (with `.dev` stripped).
  The version in `pyproject.toml` during development is e.g., `1.2.4.dev`; after
  stripping, the release version is `1.2.4`.

- **Unchanged packages**: the version from their last release tag. The tag
  `my-pkg/v1.2.3` is parsed by splitting on `/v` to extract `1.2.3`.

```python
published_versions: dict[str, str] = {}
for name in changed_names:
    published_versions[name] = changed[name].version  # already stripped
for name, info in packages.items():
    if name not in changed_names:
        tag = release_tags.get(name)
        published_versions[name] = (
            tag.split("/v")[-1] if tag and "/v" in tag else info.version
        )
```

## `deps.py:update_dep_pins`

Given a `pyproject.toml` path and a `{dep_name: version}` map, updates all
internal dependency constraints in place. Scans three sections:

1. `[project].dependencies`
2. `[project].optional-dependencies.*`
3. `[dependency-groups].*`

For each section, delegates to `_pin_dep_list`, which iterates the list, checks
each entry's canonical name against the version map, and calls `pin_dep` to
replace the specifier:

```python
def pin_dep(dep_str: str, version: str) -> str:
    req = Requirement(dep_str)
    extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
    return f"{req.name}{extras}>={version}"
```

The `write` parameter controls whether changes are flushed to disk. When
`write=False`, the function detects and returns changes without modifying the
file. This is used by `build_plan` during plan generation.

### Return value

Returns `list[tuple[str, str]]` -- pairs of `(old_spec, new_spec)` for each
dependency that was changed. Example:

```python
[("pkg-alpha>=0.1.0", "pkg-alpha>=0.1.5")]
```

Empty list means no pins needed updating.

## `deps.py:rewrite_pyproject`

Lower-level function that both sets the package version **and** pins internal
deps in a single write. Used during two pipeline phases:

1. **Pre-build version strip** -- sets the release version (strips `.dev`),
   no dep pin changes (`internal_dep_versions={}`).
2. **Post-release bump** -- sets the next dev version and pins deps to the
   just-published versions.

Uses tomlkit to preserve TOML formatting and comments.

## The write-prompt flow in `cmd_release`

`cli/release.py:cmd_release` orchestrates the user-facing pin update experience:

1. `build_plan(..., dry_run=False)` returns `pin_changes` -- a list of
   `(package_name, [(old_spec, new_spec), ...])` tuples. These were detected
   with `write=False`.

2. If `pin_changes` is non-empty, `_print_plan` displays them under a
   "Dependency pins" section.

3. The user is prompted: `"Write dependency pin updates? [y/N]"`.

4. On "y", `pipeline.py:write_dep_pins(plan)` is called, which recomputes
   published versions from the plan and calls `update_dep_pins(..., write=True)`
   for each changed package.

5. After writing, the user is instructed to commit and re-run `uvr release`:

   ```
   Commit pin updates before dispatching:
     git add -A && git commit -m 'chore: update dependency pins' && git push
     uvr release
   ```

6. On the second run, `build_plan` detects no pending pin changes (they are
   already committed), so `pin_changes` is empty and the release proceeds to
   the dispatch prompt.

### Why two passes?

The plan must be generated from the current git state to compute correct diffs.
But writing pin changes modifies files, which would change the git state. The
two-pass design (detect, prompt, write, re-run) keeps the plan generation pure
and ensures the dispatched plan matches the committed code.

## Post-release pinning in `bump_versions`

After a release, `pipeline.py:bump_versions` bumps each changed package to its
next dev version and pins its internal deps to the **just-published** versions
(not the bumped dev versions). This ensures that during development, each
package's `pyproject.toml` declares constraints that are satisfiable from PyPI:

```python
internal_dep_versions = {
    dep: published_state[dep].published_version
    for dep in pkg.info.deps
    if dep in published_state
}
rewrite_pyproject(
    Path(pkg.info.path) / "pyproject.toml",
    make_dev(new_version),         # e.g., "1.2.5.dev"
    internal_dep_versions,         # e.g., {"pkg-alpha": "0.1.5"}
)
```
