# Command Reference

## `uvr workflow init`

Scaffold the GitHub Actions release workflow.

```
uvr workflow init [--force | --upgrade | --base-only] [--editor EDITOR] [--workflow-dir DIR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--force` | -- | Overwrite existing `release.yml` with fresh defaults |
| `--upgrade` | -- | Three-way merge the latest template into an existing `release.yml` |
| `--base-only` | -- | Write merge bases to `.uvr/bases/` without touching actual files |
| `--editor` | `$VISUAL` / `$EDITOR` | Editor for conflict resolution during upgrade |
| `--workflow-dir` | `.github/workflows` | Directory to write the workflow file |

Fails if `release.yml` already exists (use `--force` to overwrite).

## `uvr skill init`

Copy bundled Claude Code skills into your project.

```
uvr skill init [--force | --upgrade | --base-only] [--editor EDITOR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--force` | -- | Overwrite existing skill files |
| `--upgrade` | -- | Three-way merge the latest skills into existing files |
| `--base-only` | -- | Write merge bases to `.uvr/bases/` without touching actual files |
| `--editor` | `$VISUAL` / `$EDITOR` | Editor for conflict resolution during upgrade |

## `uvr workflow validate`

Validate an existing `release.yml` against the `ReleaseWorkflow` model.

```
uvr workflow validate [--workflow-dir DIR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--workflow-dir` | `.github/workflows` | Directory containing the workflow file |

Reports errors for invalid structure, warnings for modified core job fields.

## `uvr workflow runners`

Manage per-package build runners.

```
uvr workflow runners [PKG] [--add RUNNER | --remove RUNNER | --clear]
```

| Argument/Flag | Description |
|---------------|-------------|
| `PKG` | Package name (omit to show all) |
| `--add RUNNER` | Add a runner for the package |
| `--remove RUNNER` | Remove a runner from the package |
| `--clear` | Remove all runners for the package |

## `uvr bump`

Bump package versions in the workspace. Use `uvr bump` to prepare the version
before releasing — the release type is determined by the version in pyproject.toml.

```
uvr bump <--all | --changed | --package PKG>
         <--major | --minor | --patch | --alpha | --beta | --rc | --post | --dev>
```

**Scope** (required, mutually exclusive):

| Flag | Description |
|------|-------------|
| `--all` | Bump all workspace packages |
| `--changed` | Bump only packages with changes since last release |
| `--package PKG` | Bump a specific package (repeatable) |

**Bump type** (required, mutually exclusive):

| Flag | Description |
|------|-------------|
| `--major` | `(X+1).0.0.dev0` |
| `--minor` | `X.(Y+1).0.dev0` |
| `--patch` | `X.Y.(Z+1).dev0` |
| `--alpha` | Enter/advance alpha cycle: `X.Y.Za(N+1).dev0` |
| `--beta` | Enter/advance beta cycle: `X.Y.Zb(N+1).dev0` |
| `--rc` | Enter/advance release candidate cycle: `X.Y.Zrc(N+1).dev0` |
| `--post` | Advance post-release number: `X.Y.Z.post(N+1).dev0` |
| `--dev` | Increment dev number: `X.Y.Z.dev(N+1)` |

## `uvr release`

Plan and execute a release. By default, generates a plan and dispatches it to
GitHub Actions. Use `--where local` to build and publish locally, or `--dry-run`
to preview without changes.

The release version is auto-detected from pyproject.toml — strip `.devN` and
publish whatever is underneath. Use `uvr bump` to change what gets released.

```
uvr release [--where {ci,local}] [--dry-run] [--dev] [--plan JSON]
            [--rebuild-all] [--python VER]
            [-y] [--skip JOB] [--skip-to JOB]
            [--reuse-run RUN_ID] [--reuse-release]
            [--no-push] [--json] [--workflow-dir DIR]
```

**Mode:**

| Flag | Default | Description |
|------|---------|-------------|
| `--where` | `ci` | `ci` dispatches to GitHub Actions, `local` builds and publishes in this shell |
| `--dry-run` | -- | Print what would be released without making changes |
| `--dev` | -- | Publish the `.devN` version as-is instead of stripping it |
| `--plan` | -- | Execute a pre-computed release plan locally |

**Build options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--rebuild-all` | -- | Rebuild all packages regardless of changes |
| `--python` | `3.12` | Python version for CI builds |

**Dispatch (CI mode):**

| Flag | Description |
|------|-------------|
| `-y`, `--yes` | Skip confirmation prompt and dispatch immediately |
| `--skip JOB` | Skip a CI job (repeatable; choices: `uvr-build`, `uvr-release`, `uvr-bump`) |
| `--skip-to JOB` | Skip all CI jobs before JOB (choices: `uvr-release`, `uvr-bump`) |
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

## `uvr install`

Install a workspace package and its internal dependencies from GitHub releases.

```
uvr install ORG/REPO/PKG[@VERSION]
```

The install spec requires the three-part `org/repo/package` form. Append
`@VERSION` to pin a specific release; otherwise the latest release is used.

## `uvr download`

Download platform-compatible wheels from GitHub releases or CI run artifacts
without installing them.

```
uvr download ORG/REPO/PKG[@VERSION] [-o DIR] [--release-tag TAG] [--run-id ID]
```

| Flag | Description |
|------|-------------|
| `-o`, `--output` | Directory to save wheels into (default: `dist/`) |
| `--release-tag` | Download from a specific GitHub release tag |
| `--run-id` | Download from a GitHub Actions run's artifacts |

When neither `--release-tag` nor `--run-id` is given, the latest release for
the package is used. Wheels are filtered by platform compatibility.
