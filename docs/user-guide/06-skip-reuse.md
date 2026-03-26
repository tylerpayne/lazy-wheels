# Skip Jobs and Reuse Artifacts

When a release partially fails, you don't have to re-run everything. Skip the jobs that already succeeded and reuse their artifacts.

## Skip individual jobs

```bash
uvr release --skip pre-build
uvr release --skip pre-build --skip post-build
```

Repeatable. Valid job names: `pre-build`, `build`, `post-build`, `pre-release`, `publish`, `finalize`, `post-release`.

## Skip to a specific job

```bash
uvr release --skip-to publish
```

Skips everything before `publish` (pre-build, build, post-build, pre-release).

## Combine both

```bash
uvr release --skip-to publish --skip finalize
```

Runs only publish and post-release.

## Reuse build artifacts from a previous run

If build succeeded but publish failed:

```bash
uvr release --skip-to publish --reuse-run 12345678
```

The publish job downloads wheels from run `12345678` instead of building them. Get the run ID from the GitHub Actions URL or `gh run list`.

## Reuse existing GitHub releases

If publish already created the releases but finalize or post-release failed:

```bash
uvr release --skip-to finalize --reuse-release
```

`--reuse-release` tells the pipeline that GitHub releases already exist. Requires both build and publish to be skipped.

## Re-run only post-release

```bash
uvr release --skip-to post-release --reuse-release
```

Common when fixing a PyPI publish configuration.

## Important: skip/reuse requires matching plan

`uvr release` always runs `build_plan()` which detects current changes. If the repo has new commits since the original release, the plan will include them. For an exact re-dispatch of the original plan, use the GitHub Actions UI directly with the original plan JSON.
---

**Under the hood:** [Release plan internals](../under-the-hood/06-release-plan.md)
