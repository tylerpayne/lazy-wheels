# Dependency Pinning

How internal dependency constraints are computed and written before a release.

See [How it works](08-architecture.md) for the user-facing explanation.

## Source files

| Module | Key functions |
|--------|---------------|
| `planner/_dependencies.py` | `set_version`, `pin_dependencies` |
| `planner/_versions.py` | `get_base_version`, `parse_tag_version` |
| `planner/_planner.py` | `ReleasePlanner.plan`, `ReleasePlanner._detect_pin_changes`, `ReleasePlanner._generate_bump_commands`, `write_dep_pins` |
| `cli/release.py` | `cmd_release` (write-prompt flow) |

## Why pins exist

When package B depends on package A, the published wheel for B must declare a
minimum version of A that is actually available. If A was released at `1.2.3` and
B still says `A>=1.0.0`, that works. But if B's code uses features added in
`1.2.3`, the constraint is wrong. uvr pins B's dependency to `A>=1.2.3` -- the
version of A that was published in the same release cycle (or the most recent
release for unchanged packages).

## Published version computation

`ReleasePlanner._published_versions` computes a `published_versions` dict for all packages:

- **Changed packages**: publish at their computed release version. The version
  in `pyproject.toml` during development is e.g., `1.2.4.dev0`; after
  stripping, the release version is `1.2.4`.

- **Unchanged packages**: the version from their last release tag. The tag
  `my-pkg/v1.2.3` is parsed by `parse_tag_version` to extract `1.2.3`.

```python
versions: dict[str, str] = {}
for name in changed_names:
    versions[name] = changed[name].version
for name, info in packages.items():
    if name not in changed_names:
        tag = release_tags.get(name)
        versions[name] = (
            parse_tag_version(tag) if tag and "/v" in tag else info.version
        )
```

## `planner/_dependencies.py:pin_dependencies`

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
file. This is used by `_detect_pin_changes` during plan generation.

### Return value

Returns `list[tuple[str, str]]` -- pairs of `(old_spec, new_spec)` for each
dependency that was changed. Example:

```python
[("pkg-alpha>=0.1.0", "pkg-alpha>=0.1.5")]
```

Empty list means no pins needed updating.

## The write-prompt flow in `cmd_release`

`cli/release.py:cmd_release` orchestrates the user-facing pin update experience:

1. `ReleasePlanner(config).plan()` returns `pin_changes` -- a list of
   `PinChange` objects containing `(package, [DepPinChange(old_spec, new_spec), ...])`.
   These were detected with `write=False`.

2. If `pin_changes` is non-empty, `_print_plan` displays them under a
   "Dependency pins" section.

3. The user is prompted: `"Write dependency pin updates? [y/N]"`.

4. On "y", `write_dep_pins(plan)` is called, which recomputes published
   versions from the plan and runs `uv add --package PKG --frozen DEP>=VER`
   for each changed dependency.

5. After writing, the user is instructed to commit and re-run `uvr release`:

   ```
   Commit pin updates before dispatching:
     git add -A && git commit -m 'chore: update dependency pins' && git push
     uvr release
   ```

6. On the second run, `_detect_pin_changes` detects no pending pin changes
   (they are already committed), so `pin_changes` is empty and the release
   proceeds to the dispatch prompt.

### Why two passes?

The plan must be generated from the current git state to compute correct diffs.
But writing pin changes modifies files, which would change the git state. The
two-pass design (detect, prompt, write, re-run) keeps the plan generation pure
and ensures the dispatched plan matches the committed code.

## Post-release pinning in `_generate_bump_commands`

After a release, the bump phase bumps each changed package to its next dev
version and pins its internal deps to the **just-published** versions (not the
bumped dev versions). This ensures that during development, each package's
`pyproject.toml` declares constraints that are satisfiable from PyPI.

`_generate_bump_commands` pre-computes internal `PinDepsCommand` invocations for
each package that has internal dependencies. These commands are embedded in the
`ReleasePlan` and executed by the workflow (or locally via `uvr jobs bump`):

```python
# Pin internal deps to just-published versions
dep_specs = [
    f"{dep}>={published_versions[dep]}"
    for dep in info.deps
    if dep in published_versions
]
if dep_specs:
    cmds.append(
        PlanCommand(
            args=["uvr", "pin-deps", "--path", pyproject] + dep_specs,
            label=f"Pin {name} deps",
        )
    )
```

The internal `PinDepsCommand` parses each `name>=version` spec and calls
`pin_dependencies()` to rewrite the target `pyproject.toml`.
