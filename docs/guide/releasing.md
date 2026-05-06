# Releasing Packages

## The standard release

```bash
uvr release
```

`uvr release` detects changes, pins dependencies, and plans a topologically ordered build, publish, and bump. It validates everything locally before dispatch. Version conflicts, stale pins, and dirty working trees are caught on your machine, not in CI. See [Architecture](../internals/architecture.md) for the full pipeline.

## Preview without releasing

```bash
uvr release --dry-run
```

Runs all detection and planning logic but makes no changes.

## Export plan as JSON

```bash
uvr release --json
```

## Bump versions before releasing

To release a minor or major version instead of patch, bump first and then release.

```bash
uvr version --bump minor
uvr release
```

Available bump types are `--bump minor`, `--bump major`, `--bump patch`, `--bump dev`, `--bump post`, and `--bump stable`. See [Managing Versions](versions.md) for the full version lifecycle.

## Publish dev versions

```bash
uvr release --dev
```

Publishes the `.devN` version as-is instead of stripping it.

## Set release notes

```bash
uvr release --release-notes pkg-alpha "Fixed the widget serializer"
uvr release --release-notes pkg-alpha @notes/alpha.md
```

The flag is repeatable for multiple packages.

## Skip confirmation

```bash
uvr release -y
```

## Build and release locally

```bash
uvr release --where local
```

Runs the full pipeline on your machine instead of dispatching to CI. Add `--no-push` to skip git push. Add `--no-commit` to skip git commit.

## Clean working tree

A clean working tree is required. `uvr release` will error if you have uncommitted changes or if your local branch is out of sync with the remote.

## Release specific packages

```bash
uvr release --packages pkg-alpha pkg-beta
```

Force specific packages to be treated as changed (and their dependents).

## Exclude specific packages

```bash
uvr release --not-packages pkg-debug pkg-internal
```

Exclude specific packages from the release even if they have changes.

## Release all packages

```bash
uvr release --all-packages
```

Treats all packages as changed regardless of what files were modified.

## Filter runners

```bash
uvr release --runners ubuntu-latest macos-latest
```

Only build on specified runner labels.

## Python version

The Python version for CI builds is configured in `[tool.uvr.config]` in your root `pyproject.toml`. See [Reference](reference.md) for all configuration keys.

## Recovery from failures

### Build failed

Nothing was published. Fix the issue and re-run.

```bash
uvr release
```

### Build succeeded, release failed

Reuse the build artifacts and skip ahead without rebuilding.

```bash
uvr release --skip-to release --reuse-run <RUN_ID>
```

Get the run ID from the GitHub Actions URL or `gh run list`.

### Release succeeded, publish or bump failed

Skip straight to bump. No `--reuse-*` flag is needed since bump does not use wheel artifacts. Use `--all-packages` so the planner treats packages with clean versions as changed.

```bash
uvr release --skip-to bump --all-packages
```

If publish failed and you want to retry it before bump, reuse the existing GitHub releases.

```bash
uvr release --skip-to publish --reuse-releases --all-packages
```

### Custom job failed

Skip the core jobs and re-dispatch.

```bash
uvr release --skip build --skip release --skip bump
```

Or re-dispatch via the GitHub Actions UI with the original plan JSON.

## Skip and reuse flags

| Flag | Description |
|------|-------------|
| `--skip JOB` | Skip a job (repeatable) |
| `--skip-to JOB` | Skip all jobs before JOB (except `validate`) |
| `--reuse-run RUN_ID` | Download artifacts from a prior CI run instead of building |
| `--reuse-releases` | Download wheels from existing GitHub releases instead of CI artifacts |
| `--all-packages` | Treat all packages as changed (needed when versions are clean after a prior release commit) |

`--reuse-run` and `--reuse-releases` are mutually exclusive.

`--reuse-run` and `--reuse-releases` are only required when `release` or `publish` will run. `--skip-to bump` does not need any `--reuse-*` flag.

## Build locally for testing

```bash
uvr build                        # build changed packages to dist/
uvr build --packages pkg-alpha   # build specific packages and their deps
uvr build --all-packages         # build everything
uvr install --dist dist/         # install from local build
```

## Install and download

```bash
uvr install pkg-alpha            # from GitHub releases
uvr install pkg-alpha@1.2.0     # specific version
uvr install --run-id 12345678   # from CI artifacts
uvr download pkg-alpha           # download wheels without installing
uvr download pkg-alpha --all-platforms
```

## Upgrade uvr

```bash
uv add --dev uv-release
uvr workflow install --upgrade   # merge template changes
uvr skill install --upgrade      # merge skill changes
```

## Clean caches

```bash
uvr clean
```
