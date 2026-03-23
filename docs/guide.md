# Guide

This is the full reference for uv-release-monorepo. If you just want to get started, the [README](../packages/uv-release-monorepo/README.md) has a three-command quick start.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) installed
- A git repository hosted on GitHub with Actions enabled
- A workspace root `pyproject.toml` with `[tool.uv.workspace]` members defined
- The [GitHub CLI](https://cli.github.com/) (`gh`) authenticated — only needed if you want `uvr release` to dispatch workflows automatically

## Setting Up Your First Release

Install uvr as a uv tool:

```bash
uv tool install uv-release-monorepo
```

Then scaffold the release workflow:

```bash
uvr init
```

This generates `.github/workflows/release.yml` from a built-in Jinja2 template. The workflow is a pure executor — it reads a `ReleasePlan` JSON and does exactly what it says. You never need to edit it by hand.

To regenerate the workflow (discarding any manual edits but preserving hooks):

```bash
uvr init
```

To regenerate and discard hooks too:

```bash
uvr init --force
```

To verify what was generated:

```bash
uvr status
```

### Configuring runners

By default every package builds on `ubuntu-latest`. If a package needs native compilation on multiple platforms, assign runners with `-m`:

```bash
uvr init -m my-native-pkg ubuntu-latest macos-14
uvr init -m another-pkg ubuntu-latest macos-14 windows-latest
```

Each `-m` takes a package name followed by one or more runner labels. Re-run `uvr init` at any time — existing runner entries are preserved and only the packages you specify are updated.

Runner configuration is stored in `[tool.uvr.matrix]` in your workspace root `pyproject.toml`.

### Filtering packages

If your workspace contains packages that shouldn't be part of the release cycle, add `[tool.uvr.config]` to your workspace root `pyproject.toml`:

```toml
[tool.uvr.config]
include = ["pkg-alpha", "pkg-beta"]   # whitelist: only these packages
exclude = ["pkg-internal"]            # blacklist: skip these packages
```

If `include` is set, only listed packages are considered. `exclude` is applied after `include`. Both are optional — omit both to manage all workspace packages.

## Releasing

When you're ready to release:

```bash
uvr release
```

This does three things:

1. **Discovery** — Scans the workspace and diffs each package against its last dev baseline tag. Only packages with new commits (plus their downstream dependents) are included.
2. **Plan** — Builds a `ReleasePlan` JSON containing every package to build, its version, precomputed release notes, and the runner matrix.
3. **Prompt** — Prints the plan as JSON and asks `Dispatch release? [y/N]`. If you confirm, the plan is dispatched to GitHub Actions via `gh workflow run`.

To skip the confirmation prompt (useful in scripts):

```bash
uvr release -y
```

### Forcing a full rebuild

```bash
uvr release --force-all
```

Ignores change detection and rebuilds every package in the workspace.

### Pinning the Python version

```bash
uvr release --python 3.11
```

Sets the Python version used in CI builds. Defaults to `3.12`.

### Using the plan without dispatching

If you don't have `gh` installed or prefer to dispatch manually, just run `uvr release` and decline the prompt. The plan JSON is printed to stdout — you can copy it into the GitHub Actions "Run workflow" UI as the `plan` input.

## CI Workflow Architecture

The generated workflow has three core jobs that run in sequence:

```
build (matrix: package × runner)
  → publish (matrix: one per changed package)
    → finalize (single job)
```

**build** — One matrix entry per (package, runner) pair. Each entry strips the `.dev0` suffix, runs `uv build`, and uploads the wheel as an artifact.

**publish** — One matrix entry per changed package. Downloads the built wheels and creates a GitHub release using `softprops/action-gh-release@v2`. Release notes are precomputed in the plan, so this job needs no Python — just `download-artifact` + the release action.

**finalize** — Bumps patch versions, commits, creates dev baseline tags, and pushes to main.

## Mixed-Architecture Builds

When a package needs wheels for multiple platforms (e.g., a C extension), uvr expands the build matrix so each runner produces its own wheel.

```bash
uvr init -m my-native-pkg ubuntu-latest macos-14
```

On release, `my-native-pkg` will be built once on `ubuntu-latest` and once on `macos-14`. Both wheels are attached to the same GitHub release.

Packages without explicit runner assignments build only on `ubuntu-latest` (pure-Python wheels are platform-independent, so one runner is enough).

You can inspect and change runner assignments at any time:

```bash
uvr status                           # see current config
uvr init -m my-native-pkg macos-14   # update runners
```

## CI Hooks

Hooks let you inject custom steps into the release workflow at four points:

| Hook | When it runs |
|---|---|
| `pre-build` | Before the build matrix starts |
| `post-build` | After all build jobs finish |
| `pre-release` | Before the publish job |
| `post-release` | After the finalize job |

Each configured hook becomes its own GitHub Actions job with the correct `needs:` chain. The full dependency chain is:

```
pre-build → build → post-build → pre-release → publish → finalize → post-release
```

Unconfigured hooks don't appear in the generated YAML at all.

### Environment variables

Every hook job exports two variables your steps can reference:

- `UVR_PLAN` — the full release plan JSON
- `UVR_CHANGED` — space-separated list of changed package names (e.g. `pkg-alpha pkg-beta`)

### Managing hooks with the CLI

**Interactive mode** — run a phase name with no action to open the interactive builder:

```bash
uvr hooks pre-build
```

**Non-interactive operations:**

```bash
# Append a run step
uvr hooks pre-build add --name "Run tests" --run "uv run pytest"

# Append a uses step with inputs
uvr hooks pre-build add --uses actions/setup-node@v4 --with node-version=20

# Add with environment variables and conditionals
uvr hooks post-release add --name "Deploy" --run "./deploy.sh" \
  --env DEPLOY_ENV=prod --if "github.ref == 'refs/heads/main'"

# Insert at a specific position (1-indexed)
uvr hooks pre-build insert 1 --name "Lint" --run "ruff check ."

# Update a step in place (only the fields you pass are changed)
uvr hooks pre-build update 2 --name "Run tests (verbose)" --run "uv run pytest -v"

# Remove by position
uvr hooks pre-build remove 1

# Remove all steps in a phase
uvr hooks pre-build clear
```

Steps support all GitHub Actions step fields: `--name`, `--run`, `--uses`, `--with KEY=VALUE` (repeatable), `--env KEY=VALUE` (repeatable), `--if`, and `--id`.

**Idempotent upserts** — pass `--id` to `add` so running the same command twice doesn't duplicate the step:

```bash
uvr hooks pre-build add --name "Run tests" --run "uv run pytest" --id run-tests
```

After any change, `uvr hooks` automatically re-renders `.github/workflows/release.yml`.

### Where hooks live

Hooks live in the generated `release.yml`, not in `pyproject.toml`. Use the CLI commands above to manage them — `uvr hooks` re-renders the workflow automatically after each change. Running `uvr init` preserves existing hooks unless you pass `--force`.

### Common hook patterns

**Gate releases on tests:**

```bash
uvr hooks pre-build add --name "Test suite" --run "uv run pytest" --id tests
```

**Lint before building:**

```bash
uvr hooks pre-build add --name "Lint" --run "ruff check ." --id lint
```

**Notify after release:**

```bash
uvr hooks post-release add --name "Slack notification" \
  --run 'curl -X POST "$SLACK_WEBHOOK" -d "{\"text\": \"Released: $UVR_CHANGED\"}"' \
  --id slack
```

## Installing from GitHub Releases

uvr can install workspace packages directly from their GitHub releases, resolving internal dependencies automatically.

### Local workspace packages

From within the repository that published the releases:

```bash
uvr install my-package           # latest version
uvr install my-package@1.2.3     # pinned version
```

This walks the workspace dependency graph, downloads the appropriate wheel for each internal dependency, and installs them all with `uv pip install`. External (PyPI) dependencies are resolved by pip from wheel metadata.

### Remote packages

To install a package published from a different repository:

```bash
uvr install acme/other-monorepo/my-package
uvr install acme/other-monorepo/my-package@1.2.3
```

Remote installs download and install the specified package directly. Your `gh` CLI must be authenticated with access to the target repository.

## How It Works

### The release flow

```
your machine                          GitHub Actions
─────────────                         ──────────────
uvr release
  ├─ scan workspace
  ├─ diff each package vs dev tag
  ├─ walk dependency graph
  ├─ precompute release notes
  ├─ expand build matrix
  ├─ print plan JSON
  └─ [confirm] dispatch plan ────────► release.yml receives plan
                                         ├─ [hook] pre-build
                                         ├─ build: matrix build per package
                                         ├─ [hook] post-build
                                         ├─ [hook] pre-release
                                         ├─ publish: one GitHub release
                                         │   per changed package
                                         │   (softprops/action-gh-release)
                                         ├─ finalize:
                                         │   ├─ bump patch versions
                                         │   ├─ commit & tag dev baselines
                                         │   └─ push
                                         └─ [hook] post-release
```

The workflow is a **pure executor**. It receives the plan as a single JSON input and follows it exactly. All intelligence — change detection, dependency resolution, matrix expansion, release notes — lives in the CLI on your machine.

### Version bumping

You control **major.minor** by editing `version` in each package's `pyproject.toml`. CI controls **patch** — after every release, it bumps the patch number and appends `.dev0`, commits, and tags the dev baseline. Between releases, your pyproject.toml always shows the development version (e.g., `0.5.2.dev0`). On release, the `.dev0` is stripped automatically.

### Dependency pinning

When a package depends on another workspace package, uvr pins the internal dependency constraint to the just-published version before releasing. This ensures that published wheels remain installable even when only a subset of packages change in the next cycle. Pin updates are applied locally during `uvr release` — if any pins change, uvr tells you to commit them before proceeding.

## Tag Structure

uvr uses two kinds of git tags:

**Release tags** like `my-pkg/v1.2.3` are created for each changed package at release time. They double as the identifier for the corresponding GitHub release (where wheels are stored).

**Dev baseline tags** like `my-pkg/v1.2.4-dev` are placed on the version-bump commit immediately after a release. They serve as the diff base for the next release — only commits after this tag are considered new work.

```
commit A   ← my-pkg/v1.0.0      (released; wheels in the my-pkg/v1.0.0 GitHub release)
commit B   ← my-pkg/v1.0.1-dev  (pyproject.toml bumped to 1.0.1.dev0; new diff base)
commit C   … normal development …
commit D   ← my-pkg/v1.0.1      (released; wheels in the my-pkg/v1.0.1 GitHub release)
commit E   ← my-pkg/v1.0.2-dev  (pyproject.toml bumped to 1.0.2.dev0; new diff base)
```

## Publishing to PyPI

The release workflow creates GitHub releases with wheels attached. If you also want to publish to PyPI, add a separate workflow that triggers on release events and uploads the wheel using [trusted publishing](https://docs.pypi.org/trusted-publishers/):

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI
on:
  release:
    types: [published]
jobs:
  publish:
    if: startsWith(github.event.release.tag_name, 'my-package/v')
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      contents: write
      id-token: write
    steps:
      - name: Download wheel from release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          mkdir dist
          gh release download "${{ github.event.release.tag_name }}" \
            --repo "${{ github.repository }}" \
            --pattern "*.whl" \
            --dir dist
      - uses: pypa/gh-action-pypi-publish@release/v1
```

This downloads the wheel directly from the GitHub release (already built at the correct version) and publishes it — no rebuilding needed.

You can also trigger it manually with `workflow_dispatch` if you add a `version` input and construct the tag from it.

## Command Reference

### `uvr init`

Scaffold the GitHub Actions release workflow.

```
uvr init [-m PKG RUNNER [RUNNER ...]] [--force] [--workflow-dir DIR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-m`, `--matrix` | — | Per-package runners. Repeatable: `-m pkg1 ubuntu-latest -m pkg2 macos-14` |
| `--force` | — | Regenerate workflow, discarding existing hooks |
| `--workflow-dir` | `.github/workflows` | Directory to write the workflow file |

### `uvr release`

Generate a release plan and optionally dispatch it to GitHub Actions.

```
uvr release [-y] [--force-all] [--python VERSION] [--workflow-dir DIR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-y`, `--yes` | — | Skip confirmation prompt and dispatch immediately |
| `--force-all` | — | Rebuild all packages regardless of changes |
| `--python` | `3.12` | Python version for CI builds |
| `--workflow-dir` | `.github/workflows` | Directory containing the workflow file |

By default, prints the plan as JSON and prompts `Dispatch release? [y/N]` before invoking `gh`. Without `gh` installed, you can still view the plan and dispatch manually via the GitHub UI.

### `uvr run`

Execute the release pipeline locally (for testing or CI).

```
uvr run [--dry-run] [--force-all] [--no-push] [--plan JSON]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | — | Print what would be released without making changes |
| `--force-all` | — | Rebuild all packages |
| `--no-push` | — | Skip git push |
| `--plan` | — | Execute a pre-computed release plan JSON |

### `uvr status`

Show the current workflow configuration, build matrix, and which packages have changed.

```
uvr status [--workflow-dir DIR]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--workflow-dir` | `.github/workflows` | Directory containing the workflow file |

### `uvr install`

Install a workspace package and its internal dependencies from GitHub releases.

```
uvr install PACKAGE[@VERSION]
uvr install ORG/REPO/PACKAGE[@VERSION]
```

### `uvr hooks`

Manage CI hook steps.

```
uvr hooks PHASE [ACTION]
```

**Phases:** `pre-build`, `post-build`, `pre-release`, `post-release`

**Actions:**

| Action | Syntax | Description |
|--------|--------|-------------|
| *(none)* | `uvr hooks PHASE` | Interactive builder |
| `add` | `uvr hooks PHASE add [--name "..."] [--run "..."] [--uses "..."] [--with K=V] [--env K=V] [--if "..."] [--id ID]` | Append a step (upsert if `--id` matches) |
| `insert` | `uvr hooks PHASE insert POS [--name "..."] [--run "..."] [--uses "..."] [--with K=V] [--env K=V] [--if "..."]` | Insert at position (1-indexed) |
| `update` | `uvr hooks PHASE update POS [--name "..."] [--run "..."] [--uses "..."] [--with K=V] [--env K=V] [--if "..."]` | Update step at position |
| `remove` | `uvr hooks PHASE remove POS` | Remove step at position |
| `clear` | `uvr hooks PHASE clear` | Remove all steps in phase |

## Configuration Reference

All uvr configuration lives in the workspace root `pyproject.toml`:

```toml
[tool.uvr.matrix]
my-native-pkg = ["ubuntu-latest", "macos-14"]
my-python-pkg = ["ubuntu-latest"]

[tool.uvr.config]
include = ["pkg-alpha", "pkg-beta"]   # optional whitelist
exclude = ["pkg-internal"]            # optional blacklist
```
