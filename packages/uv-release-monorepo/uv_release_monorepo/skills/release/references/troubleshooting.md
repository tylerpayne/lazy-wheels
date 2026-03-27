# Troubleshooting

## `uvr status` shows unexpected packages

A package may have been modified without a version bump. Check `git log --oneline -- packages/<name>` since the last release tag to confirm the changes are real. If a package changed only in dev files (tests, docs), consider whether it truly needs a release.

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

Use `--skip-to` and `--reuse-run` to resume from a specific point. See `cli.md#dispatch-options-ci-mode` for details.

```bash
# Build succeeded but publish failed — reuse artifacts
uvr release --skip-to publish --reuse-run <RUN_ID>

# Publish succeeded but finalize failed — skip build + publish
uvr release --skip-to finalize --reuse-release
```

## Main moved ahead of the release branch

If other work was merged to main between when you branched and when the release finalized, you'll see conflicts when merging back.

**What happened:** The finalize job bumps versions and pins deps on the release branch. Meanwhile, main may have new commits that touch pyproject.toml, uv.lock, or the same source files.

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

After merging, verify with `uvr status` — it should show no changed packages. If it does, the version bumps from finalize didn't land cleanly. Check pyproject.toml versions match what finalize set.

**If the merge is too messy**, an alternative is to skip the merge and cherry-pick only your pre-release commits onto main, then let the next release pick up the changes naturally.

## Rolling back a bad release

GitHub releases can be deleted, but published packages (e.g., on PyPI) generally cannot. If a broken version was published:

1. Delete the GitHub release: `gh release delete <tag> --yes`
2. Delete the tag: `git push --delete origin <tag>`
3. Fix the issue, bump the version again, and re-release
