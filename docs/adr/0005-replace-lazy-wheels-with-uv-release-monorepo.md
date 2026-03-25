# Replace lazy-wheels with uv-release-monorepo

* Status: accepted
* Date: 2026-03-25

## Context and Problem Statement

The project started as `lazy-wheels`, a monorepo release tool with a simple pipeline baked into shell scripts and a static workflow template. As the tool grew to support matrix builds, per-package releases, dependency graph resolution, and a plan+execute architecture, the name no longer reflected the scope. The tool also needed to be published to PyPI and installable via `uv tool install`. Should we continue evolving `lazy-wheels` or rewrite it as a new package?

## Decision Drivers

- **Naming**: `lazy-wheels` was a working title that described the caching behavior, not the tool's actual purpose
- **Publishability**: the new package needed a clear, descriptive name on PyPI
- **CLI ergonomics**: a short command name (`uvr`) that signals the tool's relationship to `uv`
- **Clean break**: the architecture had changed fundamentally enough that incremental migration would carry dead code

## Considered Options

- Rename `lazy-wheels` in place (keep the package, change metadata)
- Create `uv-release-monorepo` as a new package, delete `lazy-wheels`

## Decision Outcome

Chosen option: "Create `uv-release-monorepo` as a new package", because the architecture had diverged too far for a rename to be clean. The old `lazy-wheels` code was entirely replaced — different module structure, different CLI, different workflow template, different data models. A new package with a descriptive name and clean history was simpler than carrying migration baggage.

### Consequences

- Good, because `uv-release-monorepo` / `uvr` clearly communicates what the tool does and its relationship to the `uv` ecosystem
- Good, because the old `lazy-wheels` tags and releases remain in git history as a reference without polluting the new package's release timeline
- Good, because the new package started with a clean module structure, proper test suite, and typed models
- Bad, because existing users of `lazy-wheels` (if any) had no upgrade path — it was a hard break
- Bad, because historical tags use two naming schemes (`r1`-`r13` and `lazy-wheels/v*` for the old package, `uv-release-monorepo/v*` for the new)
