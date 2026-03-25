# Move Dependency Pinning to Local Planning

* Status: accepted
* Date: 2026-03-25

## Context and Problem Statement

When workspace packages depend on each other, published wheels must pin their internal dependency constraints to the just-published version. Originally, CI computed and applied these pins during the release workflow. This violated the plan+execute principle (see [ADR-0001](0001-use-plan-execute-architecture-for-releases.md)) — CI was making decisions about version numbers rather than executing a pre-computed plan. Where should internal dependency pinning be computed?

## Decision Drivers

- **Plan+execute consistency**: all release decisions should be made locally and frozen in the plan
- **Inspectability**: pin changes should be visible and reviewable before dispatch
- **Correctness**: pins must match the versions that will actually be published

## Considered Options

- CI-side pinning during the release workflow (status quo)
- Local pinning during `build_plan()` with a `BumpPlan` model

## Decision Outcome

Chosen option: "Local pinning during `build_plan()`", because it keeps CI as a pure executor. `build_plan()` pre-computes all version bumps and internal dependency pins, stores them in a `BumpPlan` within the `ReleasePlan` JSON, and CI applies them mechanically via `apply_bumps()`.

If pins change local files, `uvr release` exits and tells the user to commit the pin updates before re-running. This makes pin changes explicit and reviewable in the git history.

### Consequences

- Good, because CI no longer makes version decisions — it applies a frozen plan
- Good, because pin updates appear as explicit commits in git history, reviewable before dispatch
- Good, because the `BumpPlan` model makes version arithmetic testable in isolation
- Bad, because `uvr release` may require two runs — one to update pins, one to dispatch — adding friction to the release flow
- Bad, because the plan JSON grows larger with the `bumps` field

## Links

- Refined by [ADR-0001](0001-use-plan-execute-architecture-for-releases.md)
