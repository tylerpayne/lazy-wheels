# Support Dev, Pre, and Post Releases with Base Tags

* Status: accepted
* Date: 2026-03-26

## Context and Problem Statement

uvr currently supports only final releases. The `-dev` tag suffix is used as a diff baseline, conflicting with PEP 440 dev releases (`.dev0`, `.dev1`). Users need to publish dev builds for testing, alpha/beta/rc pre-releases for validation, and post-releases for metadata fixes. How should uvr support the full PEP 440 release lifecycle while keeping the baseline tag mechanism intact?

## Decision Drivers

- **PEP 440 compliance**: dev (`.devN`), pre (`aN`, `bN`, `rcN`), and post (`.postN`) releases are standard
- **No CI-side magic**: version changes should be visible, committable, and reviewable locally — same pattern as dep pins
- **Branch-safe tag resolution**: tags should be derivable from the pyproject.toml version, not found by searching for "the latest" — enabling post-release branches off older versions
- **Baseline tag conflict**: the current `-dev` suffix collides with actual dev release tags

## Considered Options

- CI-side version rewrite at build time (ephemeral, not committed)
- Local version rewrite before dispatch (committed, like dep pins)

## Decision Outcome

Chosen option: "Local version rewrite before dispatch", because it follows the same pattern as dependency pin updates — the user sees exactly what will change, confirms, commits, and then dispatches. No hidden CI-side transformations.

### Three design decisions

**1. Rename `-dev` baseline tags to `-base`**

The `-dev` tag suffix is repurposed for actual dev release tags. The diff baseline tag becomes `-base`:

```
v1.0.1.dev0-base    (baseline for change detection)
v1.0.1.dev0         (published dev release)
```

Baseline tags are derived from the pyproject.toml version (`f"{name}/v{version}-base"`), not found by searching. This makes them branch-safe — a post-release branch off v1.0.0 doesn't collide with v2.0.0's baseline tags.

**2. Local version rewrite with commit prompt**

Version changes happen locally before dispatch, following the dep pins pattern:

```
uvr release            strips .devN locally        prompt: "commit 1.0.1?"
uvr release --dev      no change needed            prompt: "dispatch 1.0.1.dev2?"
uvr release --pre a    rewrites to 1.0.1a0         prompt: "commit 1.0.1a0?"
uvr release --pre a    (again) bumps to 1.0.1a1    prompt: "commit 1.0.1a1?"
uvr release --post     rewrites to 1.0.0.post0     prompt: "commit 1.0.0.post0?"
uvr release --post     (again) bumps to 1.0.0.post1  prompt: "commit 1.0.0.post1?"
```

If the current version already matches the release type (e.g., already on `1.0.1a0`), the version is incremented (`a1`, `post1`, etc.) rather than rewritten. The prompt shows the exact `uv version` and `git` commands. For `--dev`, no version change is needed so the version prompt is skipped.

**3. Always bump to next `.devN` after any release**

Finalize always increments the dev version:
- After final `1.0.1`: bump to `1.0.2.dev0`
- After dev `1.0.1.dev2`: bump to `1.0.1.dev3`
- After pre `1.0.1a0`: bump to `1.0.1.dev3` (next devN in sequence)
- After post `1.0.0.post0`: bump to `1.0.0.post0.dev0`

### Version flow

```
pyproject: 1.0.0                 uvr release          tag: v1.0.0
pyproject: 1.0.1.dev0            (auto-bump)          tag: v1.0.1.dev0-base
pyproject: 1.0.1.dev0            uvr release --dev    tag: v1.0.1.dev0
pyproject: 1.0.1.dev1            (auto-bump)          tag: v1.0.1.dev1-base
pyproject: 1.0.1.dev2            uvr release --pre a  tag: v1.0.1a0
pyproject: 1.0.1.dev3            (auto-bump)          tag: v1.0.1.dev3-base
pyproject: 1.0.1.dev3            uvr release --pre a  tag: v1.0.1a1  (auto-incremented)
pyproject: 1.0.1.dev4            (auto-bump)          tag: v1.0.1.dev4-base
pyproject: 1.0.1.dev4            uvr release          tag: v1.0.1
pyproject: 1.0.2.dev0            (auto-bump)          tag: v1.0.2.dev0-base
  (user checks out v1.0.1 tag, pyproject is 1.0.1)
pyproject: 1.0.1                 uvr release --post   tag: v1.0.1.post0
pyproject: 1.0.1.post0.dev0     (auto-bump)          tag: v1.0.1.post0.dev0-base
pyproject: 1.0.1.post0.dev0     uvr release --post   tag: v1.0.1.post1  (auto-incremented)
pyproject: 1.0.1.post1.dev0     (auto-bump)          tag: v1.0.1.post1.dev0-base
```

### Consequences

- Good, because all PEP 440 release types are supported with a consistent local-commit-then-dispatch flow
- Good, because baseline tags are deterministic from pyproject.toml — no tag search, no branch confusion
- Good, because the `-base` suffix frees up `-dev` for actual dev release tags
- Good, because `--dev` releases require zero version changes (publish as-is)
- Bad, because renaming `-dev` to `-base` requires migrating existing repos (backward compat fallback mitigates this)
- Bad, because post-release flow creates compound versions (`1.0.0.post0.dev0`) that look unusual
- Bad, because `uvr release --post` requires the pyproject version to be a plain final release (no `.dev`, no `a/b/rc`) — user must check out a release tag first. This is correct per PEP 440 (post-releases are tied to final releases only).

## Links

- Refines [ADR-0002](0002-use-dev-baseline-tags-for-change-detection.md) — baseline tags renamed from `-dev` to `-base`
- Extends [ADR-0001](0001-use-plan-execute-architecture-for-releases.md) — version rewrite follows the local-plan-then-dispatch pattern
