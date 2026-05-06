# Reference

Complete CLI reference for `uvr`. Every flag and subcommand listed here matches the
CLI source of truth.

## `uvr release`

Plan and execute a release.

```
uvr release [options]
```

| Flag | Description |
|---|---|
| `--where {ci,local}` | `ci` dispatches to GitHub Actions (default). `local` runs in your shell. |
| `--dry-run` | Preview the plan without making changes. |
| `--plan JSON` | Execute a pre-computed plan instead of generating one. |
| `--all-packages` | Treat all packages as changed. |
| `--packages PKG [...]` | Force specific packages to be treated as changed. |
| `--not-packages PKG [...]` | Exclude specific packages from the release. |
| `--dev` | Publish `.devN` as-is instead of stripping it. |
| `-y`, `--yes` | Skip the confirmation prompt. |
| `--no-commit` | Skip git commit (local mode only). |
| `--no-push` | Skip git push (local mode only). |
| `--reuse-run RUN_ID` | Download artifacts from a prior CI run. |
| `--reuse-releases` | Assume GitHub releases already exist. |
| `--runners LABEL [...]` | Filter to specific CI runner labels. |
| `--skip JOB [...]` | Skip CI jobs (repeatable). |
| `--skip-to JOB` | Skip all jobs before JOB (except `validate`). |
| `--release-notes PKG NOTES` | Set release notes (inline text or `@file`). Repeatable. |
| `--json` | Print only the plan JSON and exit. |

## `uvr build`

Build changed packages locally.

```
uvr build [--all-packages] [--packages PKG [...]]
```

| Flag | Description |
|---|---|
| `--all-packages` | Build all workspace packages. |
| `--packages PKG [...]` | Build specific packages. |

## `uvr version`

Read, set, or bump package versions. With no flags, displays current versions.

```
uvr version [options]
```

**Mode** (mutually exclusive, optional):

| Flag | Description |
|---|---|
| *(none)* | Display current package versions. |
| `--set VERSION` | Set all targeted packages to an explicit version string. |
| `--bump [AXIS]` | Increment a version number. With no argument, auto-detects the last section (dev, pre-release, post, or patch) and increments it. Explicit axes: `dev`, `patch`, `minor`, `major`, `post`, `stable`. `stable` strips pre-release and dev suffixes. |

**Scope:**

| Flag | Description |
|---|---|
| `--all-packages` | Target all workspace packages. |
| `--packages PKG [...]` | Target specific packages. |
| `--not-packages PKG [...]` | Exclude specific packages. |
| `--force` | Target unchanged packages (implies `--all-packages`). |

**Options:**

| Flag | Description |
|---|---|
| `--no-pin` | Skip updating dependency pins in downstream packages. |
| `--no-commit` | Skip git commit. |
| `--no-push` | Skip git push. |

## `uvr status`

Show workspace status.

```
uvr status
```

No flags.

## `uvr configure`

Manage workspace configuration. Without arguments, shows current config.

```
uvr configure [options]
```

| Flag | Description |
|---|---|
| `--latest PKG` | Set the "Latest" package on GitHub releases. |
| `--include PKG [...]` | Include specific packages. |
| `--exclude PKG [...]` | Exclude specific packages. |
| `--remove PKG [...]` | Remove packages from include/exclude lists. |
| `--clear` | Clear all configuration. |

## `uvr configure publish`

Manage publishing configuration.

```
uvr configure publish [options]
```

| Flag | Description |
|---|---|
| `--index NAME` | PyPI index name or URL. |
| `--environment NAME` | GitHub Actions environment for publishing. |
| `--trusted-publishing VALUE` | OIDC configuration. |
| `--include PKG [...]` | Only publish these packages. |
| `--exclude PKG [...]` | Skip these packages. |
| `--remove PKG [...]` | Remove packages from lists. |
| `--clear` | Clear all publishing configuration. |

## `uvr configure runners`

Manage per-package CI runners.

```
uvr configure runners [options]
```

| Flag | Description |
|---|---|
| `--package PKG` | Package to configure. |
| `--add LABEL [...]` | Add runner labels. |
| `--remove LABEL [...]` | Remove runner labels. |
| `--clear` | Clear all runners for the package. |

## `uvr download`

Download wheels from a release.

```
uvr download [PKG] [options]
```

| Flag | Description |
|---|---|
| `package` | Package name (positional, optional). |
| `--release-tag TAG` | Specific release tag to download from. |
| `--run-id RUN_ID` | GitHub Actions run ID. |
| `--output DIR` | Output directory (default: `dist`). |
| `--repo OWNER/REPO` | GitHub repository. |
| `--all-platforms` | Download for all OS/architecture combinations. |

## `uvr install`

Install packages from wheels.

```
uvr install [PKG ...] [options]
```

| Flag | Description |
|---|---|
| `packages` | Package names (positional, variadic). |
| `--dist DIR` | Directory containing wheels. |
| `--repo OWNER/REPO` | GitHub repository. |

## `uvr workflow validate`

Validate the release workflow against the bundled template.

```
uvr workflow validate [options]
```

| Flag | Description |
|---|---|
| `--workflow-dir PATH` | Workflow directory (default: `.github/workflows`). |
| `--diff` | Show diff from template. |

## `uvr workflow install`

Install or upgrade the release workflow.

```
uvr workflow install [options]
```

| Flag | Description |
|---|---|
| `--force` | Overwrite existing workflow with the bundled template. Records the new `workflow-version`. |
| `--upgrade` | Upgrade existing workflow via three-way merge against the previously-recorded `workflow-version`. |
| `--workflow-dir PATH` | Workflow directory (default: `.github/workflows`). |
| `--editor CMD` | Editor for conflict resolution. |

Without flags, `install` scaffolds the workflow if missing and errors if it already exists. `--upgrade` requires `[tool.uvr.config].workflow-version` to be set (recorded automatically by previous `install` runs).

## `uvr skill install`

Install or upgrade Claude Code skill files.

```
uvr skill install [options]
```

| Flag | Description |
|---|---|
| `--force` | Overwrite existing skill files with the bundled templates. Records the new `skill-version`. |
| `--upgrade` | Three-way merge each existing skill file against the previously-recorded `skill-version`. |
| `--editor CMD` | Editor for conflict resolution. |

Without flags, `install` scaffolds any missing skill files. Files that already exist are left untouched unless `--upgrade` or `--force` is passed. `--upgrade` requires `[tool.uvr.config].skill-version` to be set.

## `uvr clean`

Remove build caches.

```
uvr clean
```

No flags.

## `uvr jobs`

CI-internal command. Executes a single job from the plan. Reads the plan from the
`UVR_PLAN` environment variable. Not intended for direct use.

```
uvr jobs <job_name>
```

## Configuration keys

All configuration lives in the root `pyproject.toml`.

```toml
[tool.uvr.config]
include = ["pkg-alpha"]              # package allowlist
exclude = ["pkg-internal"]           # package denylist
latest = "pkg-alpha"                 # GitHub "Latest" badge
python_version = "3.12"              # Python version for CI builds

[tool.uvr.runners]
pkg-alpha = [["ubuntu-latest"], ["macos-latest"]]

[[tool.uv.index]]
name = "pypi"                        # required for publishing
url = "https://pypi.org/simple/"
publish-url = "https://upload.pypi.org/legacy/"

[tool.uvr.publish]
index = "pypi"                       # must match a [[tool.uv.index]] name
environment = "pypi-publish"         # GitHub Actions environment
trusted-publishing = "automatic"     # "automatic", "always", or "never"
include = ["pkg-alpha"]              # only publish these
exclude = ["pkg-debug"]              # skip these

[tool.uvr.hooks]
file = "uvr_hooks.py"               # hook file (default class Hooks)
```

## CI pipeline jobs

| Job | What it does |
|---|---|
| `validate` | Validates the release plan JSON. Cannot be skipped. |
| `build` | Downloads unchanged deps, builds changed packages in topological layers. |
| `release` | Creates git tags and GitHub releases with wheel assets. |
| `publish` | Runs `uv publish` for each publishable package. |
| `bump` | Bumps to next `.dev0`, pins deps, creates baseline tags, commits, pushes. |
