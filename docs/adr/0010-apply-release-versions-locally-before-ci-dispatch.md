# Apply Release Versions Locally Before CI Dispatch

* Status: accepted
* Date: 2026-03-27

## Context and Problem Statement

`uvr release` generates a release plan containing shell commands that CI executes. Previously, version setting (`uv version X.Y.Z`) and dependency pinning (`uvr pin-deps`) were among those CI build commands — applied ephemerally during the build job but never committed. This meant release tags pointed at commits where `pyproject.toml` still contained `.dev0` versions. The release version existed only transiently in the CI build environment.

How should release versions and dependency pins be applied so that tagged commits accurately reflect the released state?

## Decision Drivers

* Release tags must point at commits that contain the actual release version in `pyproject.toml`
* The release flow should remain a single `uvr release` invocation — no manual version-setting steps

## Considered Options

* **Option A**: Apply versions and pins locally before CI dispatch (commit them to the release branch)
* **Option B**: Have CI commit the version changes before building (write + commit + push in CI, then build)
* **Option C**: Keep ephemeral CI writes but tag a different commit (create the tag after finalize rewrites versions)

## Decision Outcome

Chosen option: **Option A — apply locally before dispatch**, because it is the simplest approach that guarantees tag-to-version consistency. The planner already has access to `set_version()` and `pin_dependencies()` as local Python functions, so calling them during planning is straightforward. The committed state is what CI checks out and builds, eliminating any divergence between the tagged source and the built artifact.

### Positive Consequences

* `git checkout <tag>` yields a tree with the correct release version in `pyproject.toml`
* CI build job is simpler — it only runs `uv build`, no version manipulation
* Local `--dry-run` and `--json` can show the exact plan without side effects (gated by `dry_run` flag on `PlanConfig`)

### Negative Consequences

* `uvr release` now creates a commit and pushes before dispatching, so the working tree must be on a release branch (already enforced by the release skill)
* Aborting after `uvr release` has committed but before CI completes requires reverting the version commit

## Pros and Cons of the Options

### Option A: Apply locally before dispatch

* Good, because tags point at commits with correct versions
* Good, because CI build job has no version-writing logic
* Good, because the planner already has the functions (`set_version`, `pin_dependencies`)
* Bad, because `uvr release` now has a side effect (commit + push) before the user confirms dispatch

### Option B: CI commits before building

* Good, because tags point at commits with correct versions
* Bad, because CI needs write access to push commits back to the branch
* Bad, because adds a round-trip (CI pushes, then must re-checkout to build the committed state)
* Bad, because the plan would need to encode git commit logic as shell commands

### Option C: Tag after finalize

* Good, because no change to the build flow
* Bad, because the tag would point at a *finalize* commit (with `.dev0` versions), not the release state
* Bad, because fundamentally doesn't solve the problem — the release version still never exists in a committed state
