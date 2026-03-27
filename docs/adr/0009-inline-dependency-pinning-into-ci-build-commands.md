# Inline Dependency Pinning Into CI Build Commands

* Status: accepted
* Date: 2026-03-27

## Context and Problem Statement

[ADR-0003](0003-move-dependency-pinning-to-local-planning.md) moved dependency pinning to local planning so that CI wouldn't make version decisions. However, the two-pass flow required pin updates to be committed before the build ran. If the build later failed, the committed pins referenced a release that never happened, leaving the repo in a bad state. How should pins be applied without pre-committing them?

## Decision Drivers

* **Atomicity**: pin changes should only persist if the build succeeds
* **Plan+execute consistency**: CI must still execute pre-computed commands, not make version decisions
* **Friction**: avoid requiring two `uvr release` runs for a single release

## Considered Options

* Pre-dispatch local pinning with two-pass flow (status quo from ADR-0003)
* Embed `uvr pin-deps` commands in the build plan

## Decision Outcome

Chosen option: "Embed `uvr pin-deps` commands in the build plan", because it preserves atomicity — pins are only applied if the build succeeds — while keeping pin *detection* as a local planning task. The planner computes exact `uvr pin-deps --path <pyproject> dep>=version` commands and embeds them in the `ReleasePlan`; CI executes them mechanically.

| Criterion | Local two-pass | Inline build commands |
|---|---|---|
| Atomicity | Pins committed before build — dangling on failure | Pins applied at build time, never committed independently |
| Plan+execute | Fully local: detect + write | Detect locally, write in CI via pre-computed commands |
| Release friction | Two runs required | Single run |
| Git reviewability | Pin changes visible as a separate commit | Pins visible in plan JSON, not as a git diff |

### Consequences

* Good, because pins never land in the repo unless the release succeeds
* Good, because single-run release flow removes the two-pass friction
* Good, because pin detection remains a planning-phase task — CI makes no version decisions
* Bad, because pin changes are no longer individually visible as git commits before dispatch
* Bad, because build commands grow more complex (version set + pin + build per package)

## Links

* Refines [ADR-0003](0003-move-dependency-pinning-to-local-planning.md)
