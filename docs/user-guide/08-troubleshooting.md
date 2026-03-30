# Troubleshooting

## Resuming a failed release

When a release fails partway through, skip the jobs that already succeeded and reuse their artifacts.

### Build failed

Nothing was published — fix the issue and re-run:

```bash
uvr release
```

### Build succeeded, release failed

Reuse the build artifacts:

```bash
uvr release --skip-to uvr-release --reuse-run <RUN_ID>
```

Get the run ID from the GitHub Actions URL or `gh run list`.

### Release succeeded, bump failed

GitHub releases already exist:

```bash
uvr release --skip-to uvr-bump --reuse-release
```

### Custom job failed (e.g., PyPI publish)

Skip everything except the failed job. For a job named `pypi-publish`:

```bash
uvr release --skip uvr-build --skip uvr-release --skip uvr-bump
```

Or re-dispatch via the GitHub Actions UI with the original plan JSON.

## Skip and reuse flags

| Flag | Description |
|------|-------------|
| `--skip JOB` | Skip a job (repeatable). Any job name in the workflow. |
| `--skip-to JOB` | Skip all core jobs before JOB. Choices: `uvr-release`, `uvr-bump`. |
| `--reuse-run RUN_ID` | Download artifacts from a prior run instead of building. Requires build to be skipped. |
| `--reuse-release` | Assume GitHub releases already exist. Requires build + release to be skipped. |

`--reuse-run` and `--reuse-release` are mutually exclusive.

## `uvr release --dry-run` shows unexpected packages

A package may have changed without a version bump. Check what changed:

```bash
git log --oneline -- packages/<name>
```

If only dev files changed (tests, docs), consider whether a release is needed.

## Pin updates block the release

Commit the pin changes and re-run:

```bash
git add -A && git commit -m "chore: update dep pins" && git push
uvr release
```

## Main moved ahead of the release branch

The bump job pushed version bumps on the release branch, but main has new commits.

```bash
git checkout main
git pull --rebase
git merge --no-ff <release-branch>
# pyproject.toml versions: accept the release branch (they have the .dev bumps)
# uv.lock: regenerate with `uv sync`
git add -A && uv sync && git add uv.lock && git commit && git push
```

Verify with `uvr release --dry-run` — it should show no changed packages.

## Important: skip/reuse requires matching plan

`uvr release` always detects current changes. If the repo has new commits since the original release, the plan will differ. For an exact re-dispatch, use the GitHub Actions UI with the original plan JSON.
---

**Under the hood:** [Release plan internals](../under-the-hood/06-release-plan.md)
