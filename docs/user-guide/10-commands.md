# Command Reference

## `uvr init`

Scaffold the GitHub Actions release workflow.

```
uvr init [--force] [--workflow-dir DIR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--force` | -- | Overwrite existing `release.yml` with fresh defaults |
| `--workflow-dir` | `.github/workflows` | Directory to write the workflow file |

Fails if `release.yml` already exists (use `--force` to overwrite).

## `uvr validate`

Validate an existing `release.yml` against the `ReleaseWorkflow` model.

```
uvr validate [--workflow-dir DIR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--workflow-dir` | `.github/workflows` | Directory containing the workflow file |

Reports errors for invalid structure, warnings for modified core job fields.

## `uvr runners`

Manage per-package build runners.

```
uvr runners [PKG] [--add RUNNER | --remove RUNNER | --clear]
```

| Argument/Flag | Description |
|---------------|-------------|
| `PKG` | Package name (omit to show all) |
| `--add RUNNER` | Add a runner for the package |
| `--remove RUNNER` | Remove a runner from the package |
| `--clear` | Remove all runners for the package |

## `uvr release`

Plan and execute a release. By default, generates a plan and dispatches it to
GitHub Actions. Use `--where local` to build and publish locally, or `--dry-run`
to preview without changes.

```
uvr release [--where {ci,local}] [--dry-run] [--plan JSON]
            [--rebuild-all] [--python VER]
            [--dev | --pre {a,b,rc} | --post]
            [-y] [--skip JOB] [--skip-to JOB]
            [--reuse-run RUN_ID] [--reuse-release]
            [--no-push] [--json] [--workflow-dir DIR]
```

**Mode:**

| Flag | Default | Description |
|------|---------|-------------|
| `--where` | `ci` | `ci` dispatches to GitHub Actions, `local` builds and publishes in this shell |
| `--dry-run` | -- | Print what would be released without making changes |
| `--plan` | -- | Execute a pre-computed release plan locally |

**Build options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--rebuild-all` | -- | Rebuild all packages regardless of changes |
| `--python` | `3.12` | Python version for CI builds |

**Release type** (mutually exclusive, default: final):

| Flag | Description |
|------|-------------|
| `--dev` | Publish a dev release (as-is `.devN` version) |
| `--pre {a,b,rc}` | Publish a pre-release (alpha, beta, or rc) |
| `--post` | Publish a post-release |

**Dispatch (CI mode):**

| Flag | Description |
|------|-------------|
| `-y`, `--yes` | Skip confirmation prompt and dispatch immediately |
| `--skip JOB` | Skip a CI job (repeatable; choices: `uvr-build`, `uvr-release`, `uvr-finalize`) |
| `--skip-to JOB` | Skip all CI jobs before JOB (choices: `uvr-release`, `uvr-finalize`) |
| `--reuse-run RUN_ID` | Reuse artifacts from a prior workflow run |
| `--reuse-release` | Assume GitHub releases already exist |

**Local mode (`--where local`):**

| Flag | Description |
|------|-------------|
| `--no-push` | Skip git push after release |

**Output:**

| Flag | Default | Description |
|------|---------|-------------|
| `--json` | -- | Print the raw plan JSON |
| `--workflow-dir` | `.github/workflows` | Directory containing the workflow file |

## `uvr status`

Preview the release plan. This is an alias for `uvr release --dry-run`.

```
uvr status [--workflow-dir DIR]
```

## `uvr install`

Install a workspace package and its internal dependencies from GitHub releases.

```
uvr install ORG/REPO/PKG[@VERSION]
```

The install spec requires the three-part `org/repo/package` form. Append
`@VERSION` to pin a specific release; otherwise the latest release is used.
