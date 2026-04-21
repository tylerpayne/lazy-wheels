# Inject State Dependencies Into Intents

* Status: accepted
* Date: 2026-04-21

## Context and Problem Statement

Intents are supposed to be pure functions of state that build Plans without performing I/O. The `compute_build_job` function currently does git I/O (tag lookup via `find_release_tag`) inside the intent layer because the information it needs (which unchanged packages have release tags) is not available from the state passed in. This happens because Workspace is a monolithic object assembled once at parse time. If a piece of state was not pre-fetched into Workspace, the intent has no way to get it without breaking the pipeline's I/O boundary. How should intents declare and receive the specific state they need without performing their own I/O?

## Decision Drivers

* **I/O boundary**: intents must not perform reads. All reads belong in the states/ layer.
* **Lazy resolution**: state that is expensive or unnecessary for some intents should not be computed eagerly for all of them. The prior RepositoryContext (ADR-0014) failed because it pre-fetched everything regardless of which intent would consume it.
* **Testability**: intents should be testable by constructing only the state they actually use, not a full Workspace fixture.
* **Explicit dependencies**: which state an intent needs should be visible from its declaration, not discovered by reading its implementation.
* **Extensibility**: adding a new state type (e.g., release tags, GitHub releases) should not require modifying every existing intent or the Workspace type.

## Considered Options

* **Option A: Typed state protocols with planner resolution.** Each state type is a frozen model (e.g., `ReleaseTags`, `GitState`, `Changes`). Each intent declares its dependencies as type annotations on its `plan()` signature or as class-level metadata. The planner inspects the declarations, runs only the needed state parsers, and passes the results as kwargs.
* **Option B: State registry with lazy providers.** A registry maps state types to provider functions. Intents request state by type at construction or plan time. Providers are called lazily on first access and cached. Similar to a lightweight DI container.
* **Option C: Enrich Workspace incrementally.** Keep Workspace but make most fields optional. Each state parser adds its piece. Intents receive the same Workspace but only the fields they declared as required are guaranteed populated.

## Decision Outcome

Chosen option: **Option A (typed state protocols)**, because it enforces the I/O boundary at the type level, resolves state lazily by construction, and makes each intent's dependencies visible in its signature. It avoids the RepositoryContext mistake of eager pre-fetching while also avoiding the runtime indirection of a DI registry.

This is a staged decision. The immediate next step is to define the first few state types (`Packages`, `Changes`, `ReleaseTags`, `GitState`) and migrate one intent as a proof of concept. Full migration of all intents follows once the pattern is validated.

### Positive Consequences

* The I/O boundary between states/ and intents/ becomes enforced by the planner's dispatch logic, not just by convention
* Each intent's test only constructs the state models it actually uses. BumpIntent tests no longer need Publishing or runners fixtures
* Adding a new state type is additive. Define a frozen model, write a parser in states/, and declare it on the intents that need it. No changes to unrelated intents or the planner dispatch
* Workspace either becomes a thin container of the core state types or is eliminated entirely

### Negative Consequences

* The planner becomes more complex. It must inspect intent declarations and resolve which parsers to run
* Intent signatures change. Every intent's `plan()` method gets new parameters, breaking the current `Intent` protocol
* State types may proliferate. Drawing the right boundaries (e.g., should `runners` be its own state type or part of `Packages`?) requires judgment calls that could lead to over-granularity
* Migration is incremental. During the transition, some intents will use the old Workspace pattern and some will use the new state injection, adding temporary inconsistency

## Comparison

| Criterion | A: Typed state protocols | B: Lazy registry | C: Enriched Workspace |
|---|---|---|---|
| I/O boundary | Enforced. Planner runs parsers, intents receive frozen models | Enforced. Providers run in states/ layer | Weakly enforced. Nothing stops an intent from reading an unpopulated field |
| Lazy resolution | Yes. Planner only runs parsers for declared deps | Yes. Providers called on first access | Partial. Planner must know which fields to populate per intent |
| Testability | Good. Construct only the state models an intent needs | Good. Mock individual providers | Poor. Still need a Workspace with many optional fields |
| Explicit dependencies | Visible in intent type signature | Visible in registry requests | Hidden. Workspace has all fields, intent accesses whichever it wants |
| Extensibility | Add a new state type and parser. No changes to existing intents | Add a new provider. No changes to existing intents | Add an optional field to Workspace. May require touching parse_workspace |
| Complexity | Medium. Planner inspects annotations and dispatches | Higher. Runtime registry, lazy evaluation, caching | Low. Minimal structural change |

## Links

* Supersedes [ADR-0014: Restructure Shared Module Architecture](0014-restructure-shared-module-architecture.md) in its RepositoryContext approach
* Refines [ADR-0001: Use Plan+Execute Architecture for Releases](0001-use-plan-execute-architecture-for-releases.md) by clarifying the boundary between state reads and plan computation
