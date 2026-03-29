# Use Per-Runner Build Matrix Instead of Per-Package

* Status: accepted
* Date: 2026-03-25

## Context and Problem Statement

The v0.4.x release workflow expanded a build matrix with one job per (package, runner) pair, where each job built a single package in isolation. This broke when packages had build-time dependencies on sibling workspace packages (e.g., `pkg-beta` listing `pkg-alpha` in `[build-system] requires`). The isolated job couldn't find the sibling wheel, causing build failures. How should the CI build matrix be structured to support build-time inter-package dependencies?

## Decision Drivers

- **Build-time dependency support**: packages that depend on siblings at build time must have those wheels available
- **Runner efficiency**: avoid redundant environment setup by grouping work per runner
- **Correctness**: build order must respect the dependency graph

## Considered Options

- Per-package matrix with artifact passing between jobs
- Per-runner matrix where each runner builds all its assigned packages in dependency order

## Decision Outcome

Chosen option: "Per-runner matrix", because it solves build-time dependencies naturally. Each runner job builds all assigned packages in topological order using `uvr-steps build-all`, with `--find-links dist/` making earlier wheels available to later builds. No cross-job artifact passing needed.

### Consequences

- Good, because build-time dependencies between sibling packages work without special handling
- Good, because fewer CI jobs (one per runner instead of one per package-runner pair) means less GitHub Actions overhead
- Good, because `topo_layers()` provides a general-purpose dependency ordering primitive reusable elsewhere
- Bad, because a failure in one package on a runner blocks all subsequent packages on that runner
- Bad, because build parallelism within a single runner is lost — packages build sequentially in topo order

## Comparison

| Criterion | Per-package matrix + artifact passing | Per-runner matrix with topo ordering |
|---|---|---|
| Build-time deps | Requires explicit artifact download steps between jobs | Natural — earlier builds land in `dist/`, available via `--find-links` |
| CI job count | O(packages × runners) | O(runners) |
| Failure isolation | One package fails independently | One failure blocks remaining packages on that runner |
| Build parallelism | Full — all packages build simultaneously | Sequential within each runner |
| Complexity | High — artifact passing, dependency ordering across jobs | Low — single script, linear execution |

## Subsequent Changes

> **Note (ADR-0014):** The `graph.py` module referenced in this ADR was moved to
> `planner/_graph.py` as part of the shared module restructuring in
> [ADR-0014](0014-restructure-shared-module-architecture.md). The `topo_layers()`
> function and algorithm remain unchanged.
