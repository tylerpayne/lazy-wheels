# Use Plan+Execute Architecture for Releases

* Status: accepted
* Date: 2026-03-25

## Context and Problem Statement

uvr needs to orchestrate multi-package releases across GitHub Actions. The original `lazy-wheels` approach embedded change detection, dependency resolution, and release logic in shell scripts inside the CI workflow template. As package structures grew more complex (transitive dependencies, per-package runners, dependency pinning), the generated YAML became fragile and users had to regenerate the workflow template every time they changed their repo structure. How should release intelligence be distributed between the local CLI and CI?

## Decision Drivers

- **Reproducibility**: a release plan generated locally should produce identical results when executed in CI
- **Portability**: users with complex package structures (build-time deps, mixed runners) shouldn't need CI-specific workarounds
- **Template stability**: users shouldn't have to regenerate the workflow YAML when adding packages or changing dependencies

## Considered Options

- CI-side intelligence (status quo from `lazy-wheels`)
- Plan+execute: local CLI builds a complete plan, CI is a pure executor
- Hybrid: local CLI does discovery, CI does build/release decisions

## Decision Outcome

Chosen option: "Plan+execute", because it satisfies all three drivers — the plan is deterministic and inspectable before dispatch, CI needs no knowledge of the package graph, and the workflow template is stable across repo structure changes.

### Consequences

- Good, because the release plan is a JSON artifact that can be reviewed, diffed, and reused
- Good, because the workflow template rarely needs regeneration — hook management (`uvr hooks`) is the only reason to touch it
- Good, because `uvr release` without confirming serves as a dry run with zero CI cost
- Bad, because all intelligence lives in the `uvr` CLI — users must keep it up to date, and a bug in plan generation can't be fixed by patching CI alone
- Bad, because the plan JSON is a versioned schema (`schema_version`) that must stay backward-compatible with deployed workflows

## Comparison

| Criterion | CI-side intelligence | Plan+execute | Hybrid |
|---|---|---|---|
| Reproducibility | Low — CI re-derives state from git, results vary with timing | High — plan is a frozen snapshot | Medium — discovery is frozen, execution is not |
| Template stability | Low — template must encode all logic, changes with every feature | High — template is a thin executor | Medium — template still encodes build/release logic |
| Portability | Low — complex structures require shell workarounds in YAML | High — CLI handles all complexity natively in Python | Medium — split responsibility is harder to reason about |
| Debuggability | Hard — failures require reading CI logs and re-running | Easy — plan JSON shows exactly what will happen | Mixed |
| CLI dependency | None — CI is self-contained | Full — CLI must be installed and current | Partial |
