## IMPORTANT: After ANY Code Change

```bash
uv run poe fix     # auto-fix formatting + lint
uv run poe check   # verify lint + types
```

Run `fix` then `check` after every change. Do not skip this. Do not commit without passing `check`.

## Structure

uv workspace with a single package at `packages/uv-release`. Published to PyPI as `uv-release`, CLI entry point is `uvr`.

## Commands

```bash
uv sync                    # Install all deps
uv run poe fix             # lintfix + format
uv run poe check           # lint + typecheck
uv run poe test            # Run tests
uv run poe all             # fix + check + test
uvr status                 # Show package status
uvr release --dry-run      # Preview release plan
uvr release                # Generate plan, prompt, dispatch to GitHub Actions
```

## Before Implementing a Feature

Before starting work on a new feature, consider whether the decision qualifies as an ADR —
meaning it is hard or costly to reverse, constrains future choices, or would confuse a new
team member. If it might qualify, ask the user whether to document it with `/adr` before writing code.

## Key Conventions

- Python >=3.11. Ruff + ty config in root `pyproject.toml`.
- Single changelog at `docs/CHANGELOG.md` using [Keep a Changelog](https://keepachangelog.com/). ADRs use MADR format in `docs/adr/`.
- Version management: you own major.minor (`uv version --bump minor --directory packages/uv-release`). CI owns patch.
- Release process: see `/release` skill. Tag format: `{pkg}/v{version}` (release), `{pkg}/v{version}-base` (dev baseline).
- `uv-release` publishes to PyPI via a `post-release` hook in the release workflow.

## Writing Style (docs and prose)

- Never use emdashes, colons, or semicolons in prose. Only use full sentences. Colons in titles and headings are fine.

## Design Philosophy

### Entity-first modeling

The codebase is organized around a fixed set of frozen entity types. Each entity represents a distinct concept in the release pipeline. Adding a new entity is a significant design decision that should be discussed before implementation.

#### Nouns

| Entity | Defined in | Role |
|---|---|---|
| Version | types.py | PEP 440 version, parsed once into structured fields |
| VersionState | types.py | The 11 distinct forms a version can take |
| Tag | types.py | A git tag tied to a package and version |
| Package | types.py | A package as discovered from pyproject.toml |
| Config | types.py | Workspace-level uvr configuration |
| Publishing | types.py | Index publishing configuration |
| Hooks | types.py | User-provided lifecycle callbacks |
| Workspace | types.py | The full workspace parsed from disk |
| Change | types.py | A package that changed since its baseline |
| Release | types.py | A changed package planned for release |
| Command | types.py (base), commands.py (subclasses) | A self-executing build/release/publish step |
| Job | types.py | A named group of commands in the workflow DAG |
| Workflow | types.py | The release workflow as a DAG of jobs |
| Plan | types.py | The final pipeline output, everything needed to execute |
| PlanParams | types.py | CLI flags passed through the pipeline |
| MergeResult | types.py | Result of a three-way file merge |
| BumpType | types.py | The 9 version bump strategies |

### Frozen entities

All entities are frozen after construction. No mutation. Builders are internal to pipeline steps and never leak past them. Transformations return new instances.

### ETL-style pipeline

The pipeline isolates reads from writes. Each step has a clear verb and I/O profile. Adding a new verb is a significant design decision.

#### Verbs

| Verb | Function | I/O profile |
|---|---|---|
| parse | `parse_workspace()` | Reads filesystem |
| detect | `parse_changes()` | Reads git |
| plan | `intent.plan()` | Reads filesystem and git (never writes) |
| execute | `execute_plan()` | Writes filesystem, runs subprocesses |

Every CLI command produces a Plan. The difference is which jobs have commands. One executor consumes the Plan regardless of how it was built. The planner calls `intent.guard()` before `intent.plan()` so hooks can intercept between parse and guard.

#### Import direction

Imports follow the pipeline direction. Later steps may import from earlier steps but never the reverse. `types` and `graph` are shared and may be imported by any module.

```
types, graph, commands  (shared, imported by all)
     ↓
   states/*             (reads filesystem, git)
     ↓
   intents/*            (reads state, builds plan — never writes)
     ↓
   execute              (runs commands)
```

A module must never import from a later pipeline step. For example, `states` must not import from `intents`. Sibling imports within the same module are fine.

### TDD with parametrized tests

Tests come first. Pure functions (versioning, graph, plan modules) are tested by constructing frozen models directly with no mocks. I/O functions (parse, detect) use tmp_path fixtures with real git repos. Test matrices are explicit and exhaustive. Each test file covers one module.

### No magic strings

Entities own their string representations. Tag knows how to format tag names. Version knows how to format version strings. No code outside an entity should construct or parse that entity's string form.

### Use existing packages

Prefer established libraries over hand-rolled logic. Version parsing delegates to `packaging`. Dependency name normalization uses `packaging.utils.canonicalize_name`. Do not write ad-hoc regex for version strings or requirement parsing.

### Naming

Function names follow `verb_noun` pattern. Examples: `plan_build_job`, `detect_changes`, `compute_release_version`, `find_baseline_tag`. Use `get`/`set` for in-memory access, `read`/`write` for disk I/O. No abbreviations.

### Typed Python

Type annotations on every function signature, variable, and return. Use `Any` when unavoidable, never `object` for dynamic values. Validate with `uv run ty check packages/uv-release`.

### File organization

Public functions and methods come first, private helpers last. No cross-file private imports or access to another class's private methods, properties, or attributes. Module-level private constants may appear at the top of a file when a class definition depends on them. Never put code in `__init__.py` files. They are for re-exports only.
