# Use Dev Baseline Tags for Change Detection

* Status: accepted
* Date: 2026-03-25

## Context and Problem Statement

uvr detects which packages changed since the last release by diffing against a git tag. Originally it diffed against the release tag (`{pkg}/v{version}`), but the version-bump commit that CI creates immediately after a release always appeared as a change in the next cycle. A `_is_only_version_bump` heuristic filtered these out, but it was fragile — any commit that touched only `pyproject.toml` would be silently ignored, including legitimate configuration changes. How should uvr determine the diff baseline for change detection?

## Decision Drivers

- **Correctness**: only real work should count as a change — not automated version bumps
- **Simplicity**: the heuristic approach was brittle and hard to reason about
- **No false negatives**: legitimate `pyproject.toml` changes must not be silently filtered

## Considered Options

- Diff against release tags with `_is_only_version_bump` heuristic (status quo)
- Two-tag system: release tags for fetching wheels, dev baseline tags for diffing

## Decision Outcome

Chosen option: "Two-tag system", because it eliminates the heuristic entirely. The dev baseline tag is placed on the version-bump commit after each release, so the diff starts from exactly the right point — no filtering needed.

### Consequences

- Good, because the `_is_only_version_bump` heuristic is eliminated entirely
- Good, because legitimate `pyproject.toml` changes are never silently skipped
- Good, because the two tags serve distinct, clear purposes: `{pkg}/v{version}` identifies the release (for fetching wheels), `{pkg}/v{version}-dev` marks the diff baseline
- Bad, because there are now two tags per release per package, adding clutter to the tag namespace
- Bad, because if a dev baseline tag is missing or misplaced, change detection breaks — there is no fallback heuristic

## Comparison

| Criterion | Heuristic filtering | Two-tag system |
|---|---|---|
| Correctness | Fragile — heuristic can false-positive on legit pyproject.toml changes | Exact — diff starts at the right commit by construction |
| Simplicity | Complex — requires parsing commit contents to decide if they "count" | Simple — tag placement is mechanical, diff is a straight `git diff` |
| Failure mode | Silent: skips real changes that look like version bumps | Loud: missing tag causes an error, not silent data loss |
| Tag overhead | 1 tag per release per package | 2 tags per release per package |
