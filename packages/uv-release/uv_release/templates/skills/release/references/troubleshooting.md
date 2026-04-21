# Troubleshooting

## Pin updates block the release

If `uvr release` says pins were updated, it exits without dispatching. Commit the pin changes and re-run:

```bash
git add -A
git commit -m "chore: update dep pins"
git push
uvr release
```

## Partial release failure (some packages published, some failed)

1. Check `gh run view <RUN_ID> --log-failed` to identify which packages failed
2. Fix the root cause (usually a build error in one package)
3. Re-run `uvr release` — it will only re-publish packages that haven't been released yet

## Tags pushed but workflow didn't trigger

Verify the workflow trigger in `.github/workflows/release.yml` matches expectations. Manually dispatch if needed:

```bash
gh workflow run release.yml
```

## Custom job failed (e.g., PyPI publish)

Check the job logs:

```bash
gh run list --workflow=release.yml --limit=5
gh run view <RUN_ID> --log-failed
```

## Resuming a partially failed release

When a release fails partway through, you don't need to start over. Use `--skip`, `--skip-to`, and `--reuse-*` flags to resume from where it broke. See `cmd-release.md` for the full flag reference.

**First, identify what succeeded.** Check the failed run:

```bash
gh run view <RUN_ID> --log-failed
```

The release pipeline has three core jobs in order: **build → release → bump**. Pick the right resume strategy based on where it failed:

### Build failed

Nothing was published — just fix the issue and re-run normally:

```bash
uvr release
```

### Build succeeded, release failed

Reuse the build artifacts so you don't rebuild:

```bash
uvr release --skip-to release --reuse-run <RUN_ID>
```

`--skip-to release` skips the build job. `--reuse-run` downloads artifacts from the prior run.

### Release succeeded, publish or bump failed

GitHub releases already exist. Skip straight to bump (or publish):

```bash
uvr release --skip-to bump --all-packages
```

Bump doesn't need wheel artifacts, so `--reuse-run` and `--reuse-release` are not required. `--all-packages` is needed so the planner treats packages with clean versions as changed.

If publish failed and you need to retry it before bump:

```bash
uvr release --skip-to publish --reuse-release --all-packages
```

### Skipping custom jobs

If your workflow has custom jobs (tests, linting, etc.) and you want to skip one — for example, because you already ran checks locally:

```bash
uvr release --skip checks
```

`--skip` is repeatable. To skip multiple jobs:

```bash
uvr release --skip checks --skip docs
```

Custom jobs must check the plan's skip list in their `if` condition for this to work. See `custom-jobs.md`.

### Constraints

- `--reuse-run` and `--reuse-release` are only required when `release` or `publish` will run (they need wheel artifacts)
- `--skip-to bump` does not require any `--reuse-*` flag (bump doesn't need wheels)
- `--reuse-run` and `--reuse-release` are mutually exclusive
- Use `--all-packages` when packages have clean versions (no `.devN`) from a prior release commit

## Main moved ahead of the release branch

If other work was merged to main between when you branched and when the release completed, you'll see conflicts when merging back.

**What happened:** The bump job bumps versions and pins deps on the release branch. Meanwhile, main may have new commits that touch pyproject.toml, uv.lock, or the same source files.

**How to resolve:**

```bash
git checkout main
git pull --rebase
git merge --no-ff <release-branch>
# resolve conflicts:
#   - pyproject.toml versions: accept the release branch's versions (they have the post-release .dev bumps)
#   - uv.lock: regenerate with `uv sync` after resolving pyproject.toml
#   - source conflicts: merge normally
git add -A
uv sync
git add uv.lock
git commit
git push
```

After merging, verify the version bumps from the bump job landed cleanly. Check pyproject.toml versions match what the bump job set.

**If the merge is too messy**, an alternative is to skip the merge and cherry-pick only your pre-release commits onto main, then let the next release pick up the changes naturally.

## Package shows "changed" with +0 / -0, 0 commits

A package can be marked changed even with no file changes. This happens for two reasons.

**Transitive propagation.** If package B depends on package A (via `[project].dependencies` or `[build-system].requires`), and A has changes, B is marked dirty too. This ensures B is rebuilt against A's new version. The dependency graph includes both runtime and build-time dependencies.

**Missing baseline tag.** If no `-base` tag exists for the package (first release, or tags were deleted), it is treated as a new package and always included.

To see why a specific package was marked dirty, check its dependency graph. If it depends on a package that has real changes, the propagation is correct and the package needs rebuilding.

## Rolling back a bad release

GitHub releases can be deleted, but published packages (e.g., on PyPI) generally cannot. If a broken version was published:

1. Delete the GitHub release: `gh release delete <tag> --yes`
2. Delete the tag: `git push --delete origin <tag>`
3. Fix the issue, bump the version again, and re-release
