# Troubleshooting and Recovery

## Build succeeded, release failed

Reuse the build artifacts. Skip ahead without rebuilding.

```bash
uvr release --skip-to uvr-release --reuse-run <RUN_ID>
```

Get the run ID from the GitHub Actions URL or `gh run list`.

## Release succeeded, publish or bump failed

Skip straight to bump. No `--reuse-*` needed since bump doesn't use wheel artifacts. Use `--rebuild-all` so the planner treats packages with clean versions as changed.

```bash
uvr release --skip-to uvr-bump --rebuild-all
```

If publish failed and you want to retry it before bump.

```bash
uvr release --skip-to uvr-publish --reuse-release --rebuild-all
```

## Build failed

Nothing was published. Fix the issue and re-run.

```bash
uvr release
```

## Custom job failed

Skip the core jobs and re-dispatch.

```bash
uvr release --skip uvr-build --skip uvr-release --skip uvr-bump
```

Or re-dispatch via the GitHub Actions UI with the original plan JSON.

## Skip and reuse flags

| Flag | Description |
|------|-------------|
| `--skip JOB` | Skip a job (repeatable) |
| `--skip-to JOB` | Skip all jobs before JOB (except `uvr-validate`) |
| `--reuse-run RUN_ID` | Download artifacts from a prior CI run instead of building |
| `--reuse-release` | Download wheels from existing GitHub releases instead of CI artifacts |
| `--rebuild-all` | Treat all packages as changed (needed when versions are clean after a prior release commit) |

`--reuse-run` and `--reuse-release` are only required when `uvr-release` or `uvr-publish` will run. `--skip-to uvr-bump` does not need any `--reuse-*` flag.

`--reuse-run` and `--reuse-release` are mutually exclusive.

## Build locally for testing

```bash
uvr build                        # build changed packages to dist/
uvr build --packages pkg-alpha   # build specific packages and their deps
uvr build --rebuild-all          # build everything
uvr install --dist dist/         # install from local build
```

## Install and download

```bash
uvr install pkg-alpha            # from GitHub releases
uvr install pkg-alpha@1.2.0      # specific version
uvr install --run-id 12345678    # from CI artifacts
uvr download pkg-alpha           # download wheels without installing
uvr download pkg-alpha --all-platforms
```

## Upgrade <code class="brand-code">uvr</code>

```bash
uv add --dev uv-release
uvr workflow init --upgrade      # merge template changes
uvr skill init --upgrade         # merge skill changes
```

## Clean caches

```bash
uvr clean
```
