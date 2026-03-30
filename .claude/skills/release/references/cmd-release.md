# `uvr release`

Plan and execute a release. By default, generates a release plan and dispatches it to GitHub Actions via `gh workflow run`.

The release plan is a self-contained JSON document passed as the `plan` input to the workflow. It contains version numbers, build commands, skip lists, matrix entries, and everything CI needs to execute the release without reading git history. See `release-plan.md` for the plan schema.

## Basic usage

```bash
uvr release              # plan + dispatch to CI
uvr release --dry-run    # preview only (same as `uvr status`)
```

## How versions work

`uvr release` auto-detects the release type from the version in pyproject.toml:

| Version in pyproject.toml | Release version | Next version |
|---|---|---|
| `1.2.3.dev0` | `1.2.3` (stable) | `1.2.4.dev0` |
| `1.2.3a2.dev0` | `1.2.3a2` (pre-release) | `1.2.3a3.dev0` |
| `1.2.3.post0.dev0` | `1.2.3.post0` (post-release) | `1.2.3.post1.dev0` |

To change what gets released, use `uvr bump` before releasing:

```bash
uvr bump --all --minor       # prepare a minor release
uvr bump --all --alpha       # enter alpha pre-release cycle
uvr bump --all --post        # advance post-release number
```

## Mode flags

| Flag | Description |
|------|-------------|
| `--where {ci,local}` | `ci` dispatches to GitHub Actions (default), `local` builds in this shell |
| `--dry-run` | Print what would be released without making changes |
| `--plan JSON` | Execute a pre-computed release plan locally |

## Release type

| Flag | Description |
|------|-------------|
| *(none)* | Strip `.devN` and release whatever is underneath (default) |
| `--dev` | Dev release — publishes the current `.devN` version as-is (see `dev-releases.md`) |

## Build options

| Flag | Description |
|------|-------------|
| `--rebuild-all` | Rebuild all packages, not just changed ones |
| `--python VER` | Python version for CI builds (default: `3.12`) |

## Dispatch options (CI mode)

| Flag | Description |
|------|-------------|
| `-y, --yes` | Skip the confirmation prompt |
| `--skip JOB` | Skip a CI job (repeatable). Core jobs: `build`, `release`, `finalize`. Custom jobs can also be skipped if they check the plan's skip list in their `if` condition. |
| `--skip-to JOB` | Skip all core jobs before JOB. Choices: `release`, `finalize`. `--skip-to release` skips build; `--skip-to finalize` skips build + release. |
| `--reuse-run RUN_ID` | Reuse build artifacts from a prior workflow run. Requires `build` to be skipped. |
| `--reuse-release` | Assume GitHub releases already exist. Requires both `build` and `release` to be skipped. |

`--reuse-run` and `--reuse-release` are mutually exclusive.

## Local mode options

| Flag | Description |
|------|-------------|
| `--no-push` | Skip `git push` after a local release |

## Output options

| Flag | Description |
|------|-------------|
| `--json` | Print only the plan JSON to stdout and exit |
| `--workflow-dir DIR` | Workflow directory (default: `.github/workflows`) |

## Common patterns

```bash
# Preview the full plan
uvr release --dry-run

# Release and skip confirmation
uvr release -y

# Resume after a failed build — reuse artifacts from run 12345678
uvr release --skip-to release --reuse-run 12345678

# Resume after release succeeded but finalize failed
uvr release --skip-to finalize --reuse-release

# Skip a custom job (e.g., tests you already ran locally)
uvr release --skip checks

# Build locally instead of via CI
uvr release --where local

# Get the plan as JSON for scripting
uvr release --json
```
