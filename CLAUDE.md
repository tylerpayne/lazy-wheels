## IMPORTANT: After ANY Code Change

```bash
uv run poe fix     # auto-fix formatting + lint
uv run poe check   # verify lint + types
```

Run `fix` then `check` after every change. Do not skip this. Do not commit without passing `check`.

## Structure

uv workspace with one package.

- `packages/uv-release`. Published to PyPI as `uv-release`, CLI entry point is `uvr`. Pure dependency injection via the `diny` container. Every type is a `@singleton` with a `@provider`, resolved automatically from `sys.argv` down. There is no planner, no Intent protocol, no `provide()` or `resolve()` calls in application code.

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

The codebase is organized around a fixed set of frozen entity types defined in `types/`. Each entity represents a distinct concept in the release pipeline. Adding a new entity is a significant design decision that should be discussed before implementation.

Core entity types currently live in `uv_release/types/`:

| Entity | Role |
|---|---|
| Version | PEP 440 version, parsed once into structured fields |
| Tag | A git tag tied to a package and version |
| Package | A package as discovered from pyproject.toml |
| Pin | A dependency version pin |
| Job | Base class for named groups of commands (subclasses for DI identity) |
| Command | Self-executing build/release/publish step (subclasses in commands/) |
| BumpKind | The version bump strategies (major, minor, patch, post, dev, stable, auto) |
| PyProject | Pydantic models for pyproject.toml parsing |
| Dependency | Internal package dependency |
| Release | A changed package planned for release |

### Frozen entities

All entities are frozen after construction. No mutation. Builders are internal to pipeline steps and never leak past them. Transformations return new instances.

### Pure DI via diny

- `parse_args()` is the `@provider(ParsedArgs)`. diny resolves CLI args from `sys.argv` automatically.
- Each CLI command in `cli/` is `@inject`. The entire program is one injected function call.
- Each CLI concern (PackageSelection, DevRelease, BumpType, etc.) is a separate `@singleton` derived from `ParsedArgs` via its own `@provider`.
- `Plan` is only for `uvr release` (CI dispatch). Other commands (`build`, `bump`, `status`) resolve their Job or singleton type directly.

### Directory layout

```
uv_release/
  types/           # Pure frozen data types, no DI
  commands/        # Self-executing Command subclasses (build, publish, etc.)
  dependencies/
    shared/        # Cross-command providers (GitRepo, WorkspacePackages, BaselineTags, etc.)
    config/        # [tool.uvr.*] settings (UvrConfig, UvrPublishing, UvrRunners)
    params/        # CLI-seeded singletons (one per CLI concern)
    build/         # Build command deps (BuildPackages, PackageDependencies, BuildOrder, BuildJob)
    release/       # Release command deps (ReleaseVersions, ReleaseNotes, Plan, etc.)
    bump/          # Standalone bump deps (BumpVersions, BumpJob)
    clean/         # uvr clean deps
    configure/     # uvr configure deps
    download/      # uvr download deps
    install/       # uvr install deps
    skill/         # uvr skill deps
    workflow/      # uvr workflow deps
  cli/             # @inject entry points, zero wiring
  ui/              # Console rendering helpers
  utils/           # Pure helpers (versioning, etc.)
  templates/       # Workflow and skill templates
  execute.py       # Plan/Job executor
```

### Import direction

```
types/                (shared, imported by all)
     ↓
dependencies/shared/  (GitRepo, WorkspacePackages, tags, versioning, graph)
     ↓
dependencies/config/  (UvrConfig, UvrPublishing, UvrRunners)
dependencies/params/  (CLI-seeded singletons)
     ↓
dependencies/{build,release,bump,clean,configure,download,install,skill,workflow}/
     ↓
cli/                  (@inject entry points)
     ↓
execute.py            (runs commands)
```

No command-axis module imports from another command-axis module. Shared modules never import from command modules.

### TDD with parametrized tests

Tests come first. Tests construct singleton dependencies directly and pass them as kwargs with no mocks where possible. Integration tests use tmp_path fixtures with real git repos. Test matrices are explicit and exhaustive. Each test file covers one module.

### No magic strings

Entities own their string representations. Tag knows how to format tag names. Version knows how to format version strings. No code outside an entity should construct or parse that entity's string form.

### Use existing packages

Prefer established libraries over hand-rolled logic. Version parsing delegates to `packaging`. Dependency name normalization uses `packaging.utils.canonicalize_name`. Do not write ad-hoc regex for version strings or requirement parsing.

### Naming

Function names follow `verb_noun` pattern. Examples: `compute_build_job`, `compute_release_version`, `compute_bumped_version`. Use `get`/`set` for in-memory access, `read`/`write` for disk I/O. No abbreviations.

### Typed Python

Type annotations on every function signature, variable, and return. Use `Any` when unavoidable, never `object` for dynamic values. Validate with `uv run ty check packages/uv-release`.

### Code comments

Every provider and non-trivial function should have inline comments explaining what is happening and why. Focus on the "why" when the reasoning is not obvious from the code itself. Do not restate what the code literally does. Do not comment obvious control flow, early returns, or one-liners whose intent is clear from context. Do not omit comments to save space when they add genuine value.

### File organization

Public functions and methods come first, private helpers last. No cross-file private imports or access to another class's private methods, properties, or attributes. Module-level private constants may appear at the top of a file when a class definition depends on them. Never put code in `__init__.py` files. They are for re-exports only.
