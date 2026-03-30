# Restructure Shared Module Architecture

* Status: accepted
* Date: 2026-03-28

## Context and Problem Statement

The `shared/` package grew to 15 flat modules with scattered per-package data across 6 parallel dicts on `ReleasePlan`, functions defined far from their sole consumer, and bare `set[str]`/`dict[str, ...]` args threaded through call chains. How should we reorganize the module structure, data model, and function signatures to reflect actual dependency relationships and reduce coupling?

## Decision Drivers

* Functions should live near their sole consumer — a utility called only by the planner shouldn't be a top-level shared module
* Per-package release data (current version, release version, next version, release tag, runners, release notes) was scattered across 6 parallel structures on `ReleasePlan`, requiring callers to correlate by name
* Discovery functions returned bare collections that were passed as separate args through 3–4 layers of calls, obscuring what state the pipeline actually depends on
* Module naming was inconsistent (verb vs noun, abbreviations, missing verb prefixes on functions)

## Considered Options

* **Option A: Flat restructure** — rename files and functions in place, consolidate per-package data, but keep the flat module layout
* **Option B: Topological subpackages with context object** — group modules into subpackages by dependency layer, consolidate per-package data into `ChangedPackage`, introduce `RepositoryContext` to replace bare arg threading
* **Option C: Single-file consolidation** — merge related modules (e.g., all version/dep/graph logic into the planner file itself)

## Decision Outcome

Chosen option: **Option B**, because it makes dependency direction explicit in the file tree, eliminates parallel data structures, and replaces bare arg threading with a typed context object.

### Three changes applied together

**1. ReleasePlan redesign (schema v9).** New `ChangedPackage(PackageInfo)` model carries `current_version`, `release_version`, `next_version`, `last_release_tag`, `release_notes`, `make_latest`, and `runners` per package. Eliminates `BumpPlan`, `MatrixEntry`, `PublishEntry`, `PinChange`, `DepPinChange`. CI-facing fields (`build_matrix`, `release_matrix`) become `@computed_field` properties derived from `changed`.

**2. Module restructure by topological layer.** `planner/` subpackage owns `_versions.py`, `_dependencies.py`, `_graph.py`, `_changes.py` as private modules. `context/` subpackage owns `_packages.py`, `_releases.py`, `_baselines.py`. Standalone `deps.py`, `versions.py`, `graph.py`, `changes.py`, `discovery.py` are deleted.

**3. RepositoryContext pattern.** `build_context()` factory pre-fetches repo handle, git tags, GitHub releases, packages, release tags, and baselines into a single `RepositoryContext` model. The planner receives this context object instead of calling discovery functions and threading results as separate args.

| Criterion | Option A (flat) | Option B (topo + context) | Option C (single file) |
|---|---|---|---|
| Dependency direction visible | No — flat layout hides layers | Yes — subpackages mirror the DAG | No — everything in one file |
| Per-package data coupling | Improved (ChangedPackage) | Improved (ChangedPackage) | Improved (ChangedPackage) |
| Arg threading eliminated | No | Yes (RepositoryContext) | Partially (fewer boundaries) |
| File count | ~15 (same) | ~18 (more, but organized) | ~8 (fewer, but large) |
| Test mock complexity | Same | Higher — mock build_context or private helpers | Lower — fewer boundaries |
| Navigation overhead | Low | Medium — deeper paths | Low |

### Positive Consequences

* Each module's position in the file tree communicates what it may depend on — `planner/_versions.py` clearly belongs to the planner
* `ChangedPackage` makes per-package data self-contained — no more correlating 6 dicts by key
* `RepositoryContext` gives the planner a single typed input instead of 5+ bare args, making the "gather state" vs "compute plan" phases explicit
* Dead code (7 unused functions) removed with confidence because the DAG analysis made sole-consumer relationships obvious

### Negative Consequences

* Deeper import paths: `from .planner._versions import get_base_version` vs `from .versions import base_version`
* Test mocking is slightly more complex — mocking `build_context` returns a pre-built `RepositoryContext` rather than patching individual discovery functions
* The `context/` and `planner/` subpackage boundaries are enforced by convention (private `_` prefix), not by Python's import system
* Schema version bump to 9 breaks existing release plans — CI workflows must be regenerated via `uvr workflow init --upgrade`

## Links

* Supersedes [ADR-0012: Replace git and gh subprocesses with pygit2 and httpx](0012-replace-git-and-gh-subprocesses-with-pygit2-and-httpx.md) — the git/ subpackage further refines that decision
