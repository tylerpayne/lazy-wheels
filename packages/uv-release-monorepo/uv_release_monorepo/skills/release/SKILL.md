---
name: release
description: Release packages to GitHub via uvr. Use when user says "release", "publish packages", "cut a release", or wants to publish new package versions.
disable-model-invocation: true
---

# Releasing Packages

Prerequisites: `uvr` (`uv tool install uv-release-monorepo`) and `gh`.

If the project has existing CI checks (tests, linting, etc.) that aren't yet wired into the release workflow, see `references/custom-jobs.md` before your first release.

## 1. Branch

You must not be on main. If you are, create a release branch:

```bash
git checkout -b release/[<PACKAGE>]v<VERSION>
```

The working tree must be clean. Run `git status`. If dirty, ask the user whether to stash, commit, or abort.

## 2. Preview Changes

```bash
uvr status
```

This shows which packages are dirty (direct changes vs transitive dependents). For the full release plan with version numbers, run:

```bash
uvr release
```

This prints the plan and prompts `Dispatch release? [y/N]`. Decline (`N`) to preview without dispatching. See `references/cmd-release.md` for all flags.

Present the output to the user. For each changed package, show:
- The package name and its new version
- Why it changed (summarize the relevant commits)

Ask the user whether any packages need a minor bump instead of patch. Patch is the default — bump minor for new features, new public API, or breaking changes:

```bash
uv version --bump minor --directory packages/<package-name>
```

## 3. Review

For each changed package, verify its public API against its docs:

1. Read the current public API
2. Check each item on this list:
   - Do the package's docstrings accurately reflect the exported types and internal functionality? Audit natural language descriptions, argument lists, returns notes, code examples, and references.
   - Do all docs (READMEs, docs/, etc) accurately reflect the public API and internal functionality of the package? Audit natural language descriptions, code examples, and references.
3. Fix any discrepancies before continuing

## 4. Release

```bash
git add -A
git commit -m "Release v<VERSION>"
git push -u origin "$(git branch --show-current)"
uvr release
```

When prompted `Dispatch release? [y/N]`, answer `y`.

If `uvr release` says dependency pins were updated, commit those first and re-run:

```bash
git add -A
git commit -m "chore: update dep pins"
git push
uvr release
```

## 5. Monitor

```bash
gh run list --workflow=release.yml --limit=1
gh run watch <RUN_ID> --exit-status
```

If the workflow fails, fix the issue on the current branch, push, and re-dispatch:

```bash
git add <files>
git commit -m "Fix: <description>"
git push
uvr release
```

## 6. Verify

```bash
gh release list --limit 15       # confirm per-package releases exist
```

If something goes wrong, see `references/troubleshooting.md`.

## 7. Merge

Merge the release branch back to main — unless the branch should not be merged.

**Merge with care** in these cases:
- **Post-releases** (`--post`) — these branch from an old tag, so pyproject.toml versions will conflict with main. You can merge and accept main's versions, or cherry-pick just the fix commits. See `references/post-releases.md`.
- **Pre-releases** (`--pre`) — do not merge intermediate pre-releases. Stay on the branch through the alpha → beta → rc → final cycle, then merge after the final release. See `references/pre-releases.md`.

**Do merge** for final releases and dev releases that branched from main:

```bash
git checkout main
git pull --rebase
git merge --no-ff <release-branch> -m "Merge release branch"
git push
```

After merging, verify:

```bash
uvr status                       # should show no changed packages
```

---

## Example

User says: "Let's release the new changes"

1. Verify not on main, create `release/v0.3.0` branch
2. Run `uvr status` — shows `my-lib` is dirty (2 commits: added export, fixed parser)
3. Run `uvr release`, decline the prompt to see the full plan
4. Present to user: "my-lib will bump 0.2.1 -> 0.2.2 (patch). It has a new public export — should this be a minor bump instead?"
5. User says "yes, bump minor" — run `uv version --bump minor --directory packages/my-lib`
6. Review docstrings and docs against current API — new `Parser` class exported but not documented. Fix docs.
7. Commit, push, run `uvr release` and confirm
8. Monitor workflow, verify GitHub releases
9. Merge release branch back to main

## References

**Commands:**
- `references/cmd-init.md` — scaffold the release workflow
- `references/cmd-validate.md` — check release.yml against schema
- `references/cmd-status.md` — preview what would release
- `references/cmd-release.md` — plan and dispatch a release (all flags)
- `references/cmd-runners.md` — manage per-package build runners
- `references/cmd-install.md` — install from GitHub releases
- `references/cmd-skill-init.md` — copy Claude skills into project

**Guides:**
- `references/pipeline.md` — the three core jobs (build, publish, finalize)
- `references/release-plan.md` — what the release plan JSON contains
- `references/custom-jobs.md` — how to add your own jobs to the workflow
- `references/dev-releases.md` — publishing `.devN` versions for testing
- `references/pre-releases.md` — alpha, beta, and release candidate versions
- `references/post-releases.md` — correcting an already-released version
- `references/troubleshooting.md` — common problems and fixes
