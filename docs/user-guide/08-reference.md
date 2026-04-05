# Reference

## <code class="brand-code">uvr release</code>

```
uvr release [options]
```

| Flag | Description |
|---|---|
| `--where {ci\|local}` | `ci` dispatches to GitHub Actions (default). `local` runs in your shell. |
| `--dry-run` | Preview the plan without making changes. |
| `--plan JSON` | Execute a pre-computed plan instead of generating one. |
| `--rebuild-all` | Treat all packages as changed. |
| `--allow-dirty` | Proceed with uncommitted changes. |
| `--python VER` | Python version for CI builds (default `3.12`). |
| `--dev` | Publish `.devN` as-is instead of stripping it. |
| `--bump TYPE` | Bump all changed packages before planning. |
| `-y`, `--yes` | Skip the confirmation prompt. |
| `--skip JOB` | Skip a CI job (repeatable). |
| `--skip-to JOB` | Skip all jobs before JOB (except `uvr-validate`). |
| `--reuse-run RUN_ID` | Download artifacts from a prior CI run. |
| `--reuse-release` | Assume GitHub releases already exist. |
| `--no-push` | Skip git push (local mode only). |
| `--json` | Print only the plan JSON and exit. |
| `--release-notes PKG NOTES` | Set release notes (inline text or `@file`). Repeatable. |
| `--workflow-dir DIR` | Workflow directory (default `.github/workflows`). |

## <code class="brand-code">uvr status</code>

```
uvr status [--rebuild-all] [--workflow-dir DIR]
```

## <code class="brand-code">uvr bump</code>

```
uvr bump <type> [scope] [options]
```

**Type (required).** `--major`, `--minor`, `--patch`, `--alpha`, `--beta`, `--rc`, `--post`, `--dev`, `--stable`.

**Scope (optional).**

| Flag | Description |
|---|---|
| (default) | Changed packages only. |
| `--all` | All workspace packages. |
| `--packages PKG [...]` | Specific packages. Use `--force` to skip the changed-package guard. |

| Flag | Description |
|---|---|
| `--no-pin` | Skip updating dependency pins in downstream packages. |

## <code class="brand-code">uvr build</code>

```
uvr build [--rebuild-all] [--python VER]
```

## <code class="brand-code">uvr install</code>

```
uvr install [PKG[@VERSION] ...] [--dist DIR] [--repo ORG/REPO] [--run-id ID]
```

## <code class="brand-code">uvr download</code>

```
uvr download [PKG[@VERSION]] [-o DIR] [--release-tag TAG] [--run-id ID] [--all-platforms] [--repo ORG/REPO]
```

## <code class="brand-code">uvr workflow init</code>

```
uvr workflow init [--force | --upgrade | --base-only] [--editor EDITOR] [--workflow-dir DIR]
```

## <code class="brand-code">uvr workflow validate</code>

```
uvr workflow validate [--workflow-dir DIR] [--diff]
```

## <code class="brand-code">uvr workflow runners</code>

```
uvr workflow runners [PKG] [--add RUNNER [...] | --remove RUNNER [...] | --clear]
```

## <code class="brand-code">uvr workflow config</code>

```
uvr workflow config [--editor EDITOR] [--latest PKG]
                    [--include PKG [...] | --exclude PKG [...] | --clear] [--remove PKG [...]]
```

Without arguments, shows the current workspace config.

## <code class="brand-code">uvr workflow publish</code>

```
uvr workflow publish [--index NAME] [--environment ENV] [--trusted-publishing {automatic|always|never}]
                     [--include PKG [...] | --exclude PKG [...] | --clear] [--remove PKG [...]]
```

## <code class="brand-code">uvr skill init</code>

```
uvr skill init [--force | --upgrade | --base-only] [--editor EDITOR]
```

## <code class="brand-code">uvr clean</code>

```
uvr clean
```

## Configuration keys

```toml
[tool.uvr.config]
include = ["pkg-alpha"]              # package allowlist
exclude = ["pkg-internal"]           # package denylist
latest = "pkg-alpha"                 # GitHub "Latest" badge
editor = "code"                      # editor for conflict resolution

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
file = "uvr_hooks.py"                # hook file (default class Hook)
```

## CI pipeline jobs

| Job | What it does |
|---|---|
| `uvr-validate` | Validates the release plan JSON. Cannot be skipped. |
| `uvr-build` | Downloads unchanged deps, builds changed packages in topological layers. |
| `uvr-release` | Creates git tags and GitHub releases with wheel assets. |
| `uvr-publish` | Runs `uv publish` for each publishable package. |
| `uvr-bump` | Bumps to next `.dev0`, pins deps, creates baseline tags, commits, pushes. |
