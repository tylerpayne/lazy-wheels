# uv-release-monorepo

Push-button releases for your [uv](https://github.com/astral-sh/uv) multi-package monorepo.

- Rebuilds only changed packages (and their dependents)
- You own major.minor, CI owns patch
- One command: `uvr release`

## Installation + Usage

**Requirements:**
- [uv](https://github.com/astral-sh/uv) installed
- A git repository
- A `pyproject.toml` with `[tool.uv.workspace]` members defined

**Install**

Install as a uv tool

```bash
uv tool install uv-release-monorepo
```

**Initialize**

Run once in your repo:

```bash
uvr init
```

For mixed-architecture builds, specify per-package runners with `-m`:

```bash
uvr init -m pkg-alpha ubuntu-latest -m pkg-beta ubuntu-latest macos-14
```

Each `-m` takes a package name followed by one or more runners.

**Release**

Then when you want to release:
```bash
uvr release
# Specify a release name
uvr release -r r1
# Force all packages to rebuild
uvr release --force-all
```

## How It Works

1. **Discover** — Scans `[tool.uv.workspace]` members to find all packages and their dependencies
2. **Detect changes** — Compares each package against its dev baseline tag
3. **Propagate dirtiness** — Marks dependents of changed packages as dirty
4. **Fetch unchanged** — Downloads wheels for unchanged packages from previous GitHub releases
5. **Build changed** — Runs `uv build` only on packages that need rebuilding
6. **Publish** — Creates a GitHub Release with all wheels (changed + unchanged)
7. **Tag** — Creates per-package release tags (only after successful publish)
8. **Bump versions** — Increments patch version in each built package's `pyproject.toml`
9. **Push** — Commits version bumps, creates dev baseline tags, and pushes back to main

## Tag Structure

uvr uses three kinds of git tags:

| Tag | Example | Purpose |
|-----|---------|---------|
| **Release tag** | `r1`, `r2`, `r3` | Identifies a release. Auto-incremented unless you pass `-r`. Corresponds to a GitHub Release containing all wheels. |
| **Package tag** | `my-pkg/v1.2.3` | Created for each changed package at release time. Records which version was included in the release. |
| **Dev baseline tag** | `my-pkg/v1.2.4-dev` | Placed on the version-bump commit *after* a release. Serves as the diff baseline for the next release — only changes after this tag are considered "new work." |

### Example timeline

```
commit A   ← my-pkg/v1.0.0      (package tag: released as 1.0.0)
commit B   ← my-pkg/v1.0.1-dev  (dev baseline: version bumped to 1.0.1)
commit C   … normal development work …
commit D   … more work …
commit E   ← my-pkg/v1.0.1      (package tag: released as 1.0.1)
commit F   ← my-pkg/v1.0.2-dev  (dev baseline: version bumped to 1.0.2)
```

Change detection diffs from the dev baseline (`my-pkg/v1.0.1-dev`) to `HEAD`. This means the version-bump commit itself is excluded from the diff, so only real work triggers a rebuild.
