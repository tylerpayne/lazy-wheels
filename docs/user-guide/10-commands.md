# Command Reference

## `uvr init`

Scaffold the GitHub Actions release workflow.

```
uvr init [--force] [--workflow-dir DIR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--force` | — | Overwrite existing `release.yml` with fresh defaults |
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

Generate a release plan and optionally dispatch it to GitHub Actions.

```
uvr release [-y] [--rebuild-all] [--python VERSION] [--skip JOB] [--skip-to JOB]
            [--reuse-run RUN_ID] [--reuse-release] [--json] [--workflow-dir DIR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-y`, `--yes` | — | Skip confirmation prompt and dispatch immediately |
| `--rebuild-all` | — | Rebuild all packages regardless of changes |
| `--python` | `3.12` | Python version for CI builds |
| `--skip` | — | Skip a job (repeatable) |
| `--skip-to` | — | Skip all jobs before the named job |
| `--reuse-run` | — | Download build artifacts from a previous workflow run |
| `--reuse-release` | — | Assume GitHub releases already exist |
| `--json` | — | Also print the raw plan JSON |
| `--workflow-dir` | `.github/workflows` | Directory containing the workflow file |

## `uvr run`

Execute the release pipeline locally (for testing or CI).

```
uvr run [--dry-run] [--rebuild-all] [--no-push] [--plan JSON]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | — | Print what would be released without making changes |
| `--rebuild-all` | — | Rebuild all packages |
| `--no-push` | — | Skip git push |
| `--plan` | — | Execute a pre-computed release plan JSON |

## `uvr status`

Show the current workflow configuration, build matrix, and which packages have changed.

```
uvr status [--workflow-dir DIR]
```

## `uvr install`

Install a workspace package and its internal dependencies from GitHub releases.

```
uvr install PACKAGE[@VERSION]
uvr install ORG/REPO/PACKAGE[@VERSION]
```
