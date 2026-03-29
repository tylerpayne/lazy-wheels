# Allow Dev Release From Clean Versions

* Status: accepted
* Date: 2026-03-29

## Context and Problem Statement

`uvr release --dev` rejected packages whose pyproject.toml version lacked a `.devN` suffix, requiring users to manually run `uv version X.Y.Z.dev0` first. All other release types (`--pre a`, `--pre b`, `--pre rc`, `--post`) auto-append their suffix to clean versions. This inconsistency confused users.

## Decision Drivers

* Consistency: every release type should handle clean versions the same way
* Fewer manual steps: no reason to require a preparatory version bump

## Decision Outcome

`--dev` now auto-appends `.dev0` to clean versions instead of rejecting them. `1.0.1` + `--dev` produces `1.0.1.dev0`, matching how `--pre a` on `1.0.1` produces `1.0.1a0`.

### Positive Consequences

* All release types are consistent — no special-casing for `--dev`
* One fewer manual step in the dev release workflow

### Negative Consequences

* Users who relied on the rejection as a safety net (preventing accidental dev releases from non-dev branches) lose that guard. The risk is low since `--dev` is an explicit opt-in flag.

## Links

* Amends [ADR-0008: Support PEP 440 release types](0008-support-pep-440-release-types.md) — relaxes the dev release precondition
