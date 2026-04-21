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
- `uv-release` publishes to PyPI via trusted publishing in the release workflow.

## Writing Style (docs and prose)

- Never use emdashes, colons, or semicolons in prose. Only use full sentences. Colons in titles and headings are fine.

## Design Philosophy

### Entity-first modeling

The codebase is organized around a fixed set of frozen entity types. Each entity represents a distinct concept in the release pipeline. Adding a new entity is a significant design decision that should be discussed before implementation.

#### Entities (types.py)

| Entity | Role |
|---|---|
| Version | PEP 440 version, parsed once into structured fields |
| VersionState | The 11 distinct forms a version can take |
| Tag | A git tag tied to a package and version |
| Package | A package as discovered from pyproject.toml |
| Config | Workspace-level uvr configuration |
| Publishing | Index publishing configuration |
| Hooks | User-provided lifecycle callbacks |
| Change | A package that changed since its baseline |
| Release | A changed package planned for release |
| Command | A self-executing build/release/publish step (base in types.py, subclasses in commands.py) |
| Job | A named group of commands in the workflow DAG |
| Plan | The final pipeline output, everything needed to execute |
| PlanParams | CLI flags passed through the pipeline (not a State) |
| MergeResult | Result of a three-way file merge |
| BumpType | The 9 version bump strategies |
| Intent | Protocol for all intent types (guard + plan methods) |

#### States (states/)

State types own their I/O via a parse() classmethod. Dependencies are declared as type hints on parse() and resolved recursively by the planner. Adding a new State is straightforward. Adding a new entity is a significant design decision.

| State | Defined in | Dependencies | Role |
|---|---|---|---|
| Workspace | states/workspace.py | (none) | Package map and root path, parsed from pyproject.toml |
| UvrState | states/uvr_state.py | (none) | Config, publishing, runners, editor, uvr version |
| Worktree | states/worktree.py | GitRepo | Git cleanliness and GitHub remote identity |
| Changes | states/changes.py | Workspace, PlanParams, GitRepo | Packages that changed since their baselines |
| ReleaseTags | states/release_tags.py | Workspace, GitRepo | Verified release tags for unchanged packages |
| LatestReleaseTags | states/github.py | Worktree | Latest release tags per package from GitHub API |
| WorkflowState | states/workflow.py | (none) | Workflow template, file content, merge base |
| SkillState | states/skill.py | (none) | Skill templates, merge bases, file existence |

### Frozen entities

All entities are frozen after construction. No mutation. Builders are internal to pipeline steps and never leak past them. Transformations return new instances.

### State + Intent pipeline

The pipeline isolates reads from writes. States own all I/O via parse() classmethods. Intents are pure functions of state that produce Plans. The planner resolves state dependencies recursively.

#### Verbs

| Verb | Where | I/O profile |
|---|---|---|
| parse | State.parse() classmethods | Reads filesystem, git, GitHub API |
| guard | Intent.guard() | Pure. Validates state, raises ValueError on failure |
| plan | Intent.plan() | Pure. Builds a Plan from resolved state |
| execute | execute_plan() | Writes filesystem, runs subprocesses |

Every CLI command produces a Plan. The difference is which jobs have commands. One executor consumes the Plan regardless of how it was built. The planner calls intent.guard() before intent.plan() so hooks can intercept between parse and guard.

#### Dependency injection

Intents declare state dependencies as keyword-only parameters on guard() and plan(). The planner inspects type hints and recursively resolves each State via its parse() classmethod. PlanParams and GitRepo are seeded into the cache. States declare their own dependencies the same way.

```python
class Changes(State):
    @classmethod
    def parse(cls, *, workspace: Workspace, params: PlanParams, git_repo: GitRepo) -> Changes: ...

class BuildIntent(BaseModel):
    def plan(self, *, workspace: Workspace, changes: Changes, release_tags: ReleaseTags) -> Plan: ...
```

#### Import direction

Imports follow the pipeline direction. Later steps may import from earlier steps but never the reverse. `types`, `graph`, and `commands` are shared and may be imported by any module. Intents import State types from states/ for type annotations only (never calling I/O directly).

```
types, graph, commands  (shared, imported by all)
     ↓
   git                  (GitRepo singleton, imported by states)
     ↓
   states/*             (State types with parse(), owns all I/O)
     ↓
   intents/*            (pure functions of state, builds plans, no I/O)
     ↓
   planner              (resolves state deps, calls guard + plan)
     ↓
   execute              (runs commands)
```

A module must never import from a later pipeline step. For example, `states` must not import from `intents`. Sibling imports within the same step are fine. State files contain only their State class and private helpers.

### TDD with parametrized tests

Tests come first. Intent tests construct State objects directly and pass them as kwargs with no mocks. State integration tests use tmp_path fixtures with real git repos. Test matrices are explicit and exhaustive. Each test file covers one module.

### No magic strings

Entities own their string representations. Tag knows how to format tag names. Version knows how to format version strings. No code outside an entity should construct or parse that entity's string form.

### Use existing packages

Prefer established libraries over hand-rolled logic. Version parsing delegates to `packaging`. Dependency name normalization uses `packaging.utils.canonicalize_name`. Do not write ad-hoc regex for version strings or requirement parsing.

### Naming

Function names follow `verb_noun` pattern. Examples: `compute_build_job`, `compute_release_version`, `compute_plan`. State types use `parse` as their classmethod name. Use `get`/`set` for in-memory access, `read`/`write` for disk I/O. No abbreviations.

### Typed Python

Type annotations on every function signature, variable, and return. Use `Any` when unavoidable, never `object` for dynamic values. Validate with `uv run ty check packages/uv-release`.

### File organization

Public functions and methods come first, private helpers last. No cross-file private imports or access to another class's private methods, properties, or attributes. Module-level private constants may appear at the top of a file when a class definition depends on them. Never put code in `__init__.py` files. They are for re-exports only.
