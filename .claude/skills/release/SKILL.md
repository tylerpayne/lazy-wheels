---
name: release
description: Release packages to GitHub via uvr. Use when user says "release", "publish packages", "cut a release", or wants to publish new package versions.
disable-model-invocation: true
---

# Releasing Packages

## Before You Start

**You must not be on main.** If you are, create a release branch:

```bash
git checkout -b release/v<VERSION>
```

**The working tree must be clean.** Run `git status`. If dirty, ask the user whether to stash, commit, or abort.

**Package filtering** is controlled by `[tool.uvr.config]` include/exclude in the root `pyproject.toml`. If `uvr status` shows packages that shouldn't be released, update the config before continuing.

## 1. Preview Changes

Run a quick check of what has changed:

```bash
uvr status
```

This shows which packages are dirty (direct changes vs transitive dependents). For the full release plan with version numbers and release notes, run:

```bash
uvr release
```

This prints the plan JSON and prompts `Dispatch release? [y/N]`. Decline (`N`) to preview without dispatching.

Present the output to the user. For each changed package, show:
- The package name and its new version
- Why it changed (summarize the relevant commits)

Ask the user whether any packages need a minor bump instead of patch. Patch is the default — bump minor for new features, new public API, or breaking changes:

```bash
uv version --bump minor --directory packages/<package-name>
```

## 2. Review

For each changed package, verify its public API against its docs:

1. Read `__init__.py` (and any `__all__` definitions) to get the current public API
2. Read the package's README
3. Check each item on this list:
   - Are all publicly exported classes, functions, and constants mentioned in the README?
   - Were any exports renamed or removed since the last release? If so, is the README updated?
   - Do any new exports have required parameters or usage patterns that need documenting?
   - Are code examples in the README still valid against the current API?
4. Fix any discrepancies before continuing

## 3. ADR Check

Review the changes since the last release for architectural decisions that should be recorded — decisions that are hard or costly to reverse, constrain future choices, or would confuse a new team member.

For each changed package, scan the commits since the last release tag:

```bash
git log --oneline <pkg>/v<last-version>-dev..HEAD -- packages/<pkg>
```

If any commits introduce significant design choices (new data models, dependency additions, API shape changes, CI pipeline changes), ask the user whether to document them with the `/adr` skill before continuing.

Do not skip this step. ADRs are easier to write while the decision is fresh.

## 4. CHANGELOG

Use the `/changelog` skill to cut a release version entry in `docs/CHANGELOG.md`.
Provide the version number (e.g., `v0.5.1`). The skill will:
- Move `[Unreleased]` entries into a new version section with today's date
- Review `git log` since the last release tag for any missing entries
- Leave an empty `[Unreleased]` heading at the top

## 5. Release

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

## 6. Monitor

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

## 7. Verify

```bash
git checkout main && git pull
uvr status                       # should show no changed packages
gh release list --limit 15       # confirm per-package releases exist
```

If `uv-release-monorepo` was part of this release, check the post-release job logs to confirm PyPI publish succeeded.

## Example

User says: "Let's release the new changes"

1. Verify not on main, create `release/v0.5.1` branch
2. Run `uvr status` — shows `uv-release-monorepo` is dirty (3 commits: added hook upsert, fixed pin logic)
3. Run `uvr release`, decline the prompt to see the full plan
4. Present to user: "uv-release-monorepo will bump 0.5.0 -> 0.5.1 (patch). It has a new hook feature — should this be a minor bump instead?"
5. User says "yes, bump minor" — run `uv version --bump minor --directory packages/uv-release-monorepo`
6. Review `__init__.py` against README — new `HookUpsert` class exported but not documented. Fix README.
7. ADR check: the hook upsert feature introduces an `--id` convention for step identity — ask user if this warrants an ADR
8. Use `/changelog` to cut the `v0.6.0` entry in `docs/CHANGELOG.md`
9. Commit, push, run `uvr release` and confirm
10. Monitor workflow, verify GitHub releases and PyPI

Result: `uv-release-monorepo v0.6.0` published to GitHub Releases and PyPI.

## Prerequisites

Before starting, verify these tools are available:
- `uvr` — run `uvr --version`. If missing: `uv tool install uv-release-monorepo`.
- `gh` — run `gh --version`. If missing: `brew install gh` then `gh auth login`.

## Troubleshooting

### `uvr status` shows unexpected packages
A package may have been modified without a version bump. Check `git log --oneline -- packages/<name>` since the last release tag to confirm the changes are real. If a package changed only in dev files (tests, docs), consider whether it truly needs a release.

### Pin updates block the release
If `uvr release` says pins were updated, it exits without dispatching. Commit the pin changes and re-run:
```bash
git add -A
git commit -m "chore: update dep pins"
git push
uvr release
```

### Partial release failure (some packages published, some failed)
1. Check `gh run view <RUN_ID> --log-failed` to identify which packages failed
2. Fix the root cause (usually a build error in one package)
3. Re-run `uvr release` — it will only re-publish packages that haven't been released yet

### Tags pushed but workflow didn't trigger
Verify the workflow trigger in `.github/workflows/release.yml` matches expectations. Manually dispatch if needed:
```bash
gh workflow run release.yml
```

### PyPI publish failed
PyPI publishing runs as a `post-release` hook in the release workflow. Check the post-release job logs:
```bash
gh run list --workflow=release.yml --limit=5
gh run view <RUN_ID> --log-failed
```
Ensure trusted publishing is configured on PyPI for this repository and that `id-token: write` is in the workflow permissions.

### Rolling back a bad release
GitHub releases can be deleted, but published PyPI packages cannot be un-published. If a broken version was published:
1. Delete the GitHub release: `gh release delete <tag> --yes`
2. Delete the tag: `git push --delete origin <tag>`
3. Fix the issue, bump the version again, and re-release
