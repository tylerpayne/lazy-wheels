# lazy-wheels

CI release workflow that only rebuilds changed packages in your multi-package uv monorepo.

## Why lazy-wheels?

Managing versions across multiple packages in a monorepo is painful. lazy-wheels makes it simple: **you own major.minor, CI owns patch**. When you're ready for a breaking change or new feature, bump the major or minor version yourself. For everything else, CI automatically increments patch versions after each release.

Your `main` branch always stays one patch version ahead of the latest release. This means HEAD is always releasable, version numbers are always increasing, and you never have to think about patch versions again. Change detection uses per-package git tags, so only packages with actual changes (or dependencies on changed packages) get rebuilt.

## Installation

```bash
pip install lazy-wheels
```

Or with uv:

```bash
uv add lazy-wheels
```

## Usage

### Initialize

Scaffold the GitHub Actions workflow into your repo:

```bash
lazy-wheels init
```

This creates `.github/workflows/release.yml` configured for your uv workspace.

**Requirements:**
- A git repository
- A `pyproject.toml` with `[tool.uv.workspace]` members defined

### Triggering a Release

**Option 1: GitHub CLI (direct)**

```bash
gh workflow run release.yml
gh workflow run release.yml -f release=r1
gh workflow run release.yml -f force_rebuild_all=true
```

**Option 2: lazy-wheels CLI (shorthand)**

```bash
lazy-wheels release
lazy-wheels release -r r1
lazy-wheels release --force-all
```

Both methods trigger the same GitHub Actions workflow.

### Workflow Inputs

| Input | Description |
|-------|-------------|
| `release` | Release tag (e.g., `r1`, `r2`). Auto-generates if not provided. |
| `force_rebuild_all` | Rebuild all packages regardless of changes. |

## How It Works

1. **Discover** — Scans `[tool.uv.workspace]` members to find all packages and their dependencies
2. **Detect changes** — Compares each package against its last release tag (`{pkg}/v{version}`)
3. **Propagate dirtiness** — Marks dependents of changed packages as dirty (transitive rebuild)
4. **Fetch unchanged** — Downloads wheels for unchanged packages from previous GitHub releases
5. **Build changed** — Runs `uv build` only on packages that need rebuilding
6. **Tag** — Creates per-package version tags (e.g., `my-pkg/v1.2.3`)
7. **Bump versions** — Increments patch version in each built package's `pyproject.toml`
8. **Publish** — Creates a GitHub Release with all wheels (changed + unchanged)
9. **Push** — Commits version bumps and pushes tags

### Version Flow Example

```
Before release:  my-pkg 1.2.3  (in pyproject.toml)
                      ↓
     Release r5:  my-pkg/v1.2.3 tag created, wheel built
                      ↓
 After release:  my-pkg 1.2.4  (bumped, committed, pushed)
                      ↓
   Next release:  my-pkg/v1.2.4 tag created (if changed)
```
