# Use Post-Release Hook for PyPI Publishing

* Status: accepted
* Date: 2026-03-25

## Context and Problem Statement

PyPI publishing for `uv-release-monorepo` was originally handled by a separate `publish.yml` workflow. This workflow went through multiple iterations — first triggering on `release` events (which `GITHUB_TOKEN`-created releases don't fire), then on tag pushes with glob patterns excluding `-dev` tags. Neither approach worked reliably. Tag-push triggers also don't fire when tags are created by the release workflow itself using `GITHUB_TOKEN`. How should PyPI publishing be integrated into the release pipeline?

## Decision Drivers

- **Reliability**: publishing must actually trigger when a release happens — no silent failures from GitHub event limitations
- **Simplicity**: avoid maintaining a separate workflow with its own trigger logic and failure modes
- **Consistency with plan+execute**: the release pipeline already has a hook system designed for exactly this kind of post-release action

## Considered Options

- Separate `publish.yml` workflow triggered by tag pushes (status quo)
- Separate `publish.yml` workflow triggered by `release` events
- Post-release hook in `release.yml` via `uvr hooks`

## Decision Outcome

Chosen option: "Post-release hook", because it runs as part of the same workflow that creates the release — no trigger indirection, no event suppression issues, and the wheels are already available as artifacts. The hook system exists precisely for this use case.

### Consequences

- Good, because publishing is guaranteed to run after a successful release — no reliance on GitHub event propagation
- Good, because `publish.yml` can be deleted — one fewer workflow to maintain
- Good, because the hook has access to `$UVR_PLAN` and `$UVR_CHANGED`, making it easy to conditionally publish only specific packages
- Good, because hook configuration is visible via `uvr hooks post-release` and version-controlled in `release.yml`
- Bad, because publishing is now coupled to the release workflow — a PyPI publish failure could block the post-release hook job, though finalize (version bumps, tags) has already completed by this point
- Bad, because re-publishing requires re-running the entire release workflow, not just a standalone workflow

## Comparison

| Criterion | Tag-push trigger | Release event trigger | Post-release hook |
|---|---|---|---|
| Reliability | Broken — `GITHUB_TOKEN` tags don't fire push events | Broken — `GITHUB_TOKEN` releases don't fire release events | Guaranteed — runs in the same workflow |
| Maintenance | Separate workflow with its own trigger logic | Separate workflow with its own trigger logic | Inline in release.yml, managed by `uvr hooks` |
| Re-publishability | Can manually dispatch | Can manually dispatch | Must re-run full release workflow |
| Wheel availability | Must download from GitHub release | Must download from GitHub release | Already available as workflow artifacts |

## Links

- Extends [ADR-0001](0001-use-plan-execute-architecture-for-releases.md) — hooks are part of the plan+execute architecture
