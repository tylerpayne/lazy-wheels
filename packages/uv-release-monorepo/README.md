# uv-release-monorepo

Push-button releases for your [uv](https://github.com/astral-sh/uv) multi-package monorepo. It rebuilds only the packages that changed, creates one GitHub release per package, and handles version bumping automatically. You own major.minor; CI owns patch.

## Why

Releasing from a monorepo is tedious. You have to figure out which packages actually changed, build the right ones, tag them, bump versions, and publish — without forgetting a transitive dependent three levels deep. Multiply that by a matrix of OS runners and it stops being something you do by hand.

uvr turns the whole thing into one command. It diffs against the last release, walks the dependency graph, builds a plan, and hands it to GitHub Actions. Unchanged packages keep their existing wheels. You stay in control of major and minor versions; CI owns the patch number.

## Quick Start

```bash
uv tool install uv-release-monorepo   # install the CLI
uvr init                               # generate .github/workflows/release.yml
uvr release                            # detect changes, build, and publish
```

You need [uv](https://github.com/astral-sh/uv), a GitHub repo with Actions enabled, and a `pyproject.toml` with `[tool.uv.workspace]` members defined.

## What You Can Do

### Release only what changed

```bash
uvr release            # build and publish changed packages
uvr release --dry-run  # preview the plan without dispatching
uvr release --force-all  # rebuild everything regardless of changes
```

uvr scans your workspace, diffs each package against its last dev baseline tag, and builds only what's new — plus anything downstream in the dependency graph.

### Build for multiple architectures

```bash
uvr init -m my-native-pkg ubuntu-latest macos-14
```

Each `-m` assigns one or more GitHub Actions runners to a package. Re-run `uvr init` to update runners; existing entries are preserved.

### Run tests or lints in CI

Hooks let you inject steps at four points in the release pipeline: `pre-build`, `post-build`, `pre-release`, and `post-release`.

```bash
uvr hooks pre-build add --name "Run tests" --run "uv run pytest"
```

Every hook job has access to `$UVR_PLAN` (the full release plan JSON) and `$UVR_CHANGED` (space-separated list of changed packages). See the [full guide](../../docs/guide.md) for all hook operations.

### Install packages from GitHub releases

```bash
uvr install my-package           # latest version, resolves internal deps
uvr install my-package@1.2.3     # pinned version
uvr install acme/other-repo/pkg  # from another repository
```

This resolves the full dependency graph, downloads the appropriate wheels, and installs them with `uv pip install`.

### Check your configuration

```bash
uvr status
```

## How It Works

`uvr release` runs on your machine. It scans the workspace, detects which packages changed since their last dev baseline tag, expands the build matrix, and serializes a `ReleasePlan` JSON. That plan is dispatched to GitHub Actions as a single input — the workflow is a pure executor that makes no decisions of its own.

On CI, a matrix job builds each changed package on its configured runners. The release job then downloads unchanged wheels from their existing GitHub releases, publishes a new release per changed package, bumps patch versions, commits, tags dev baselines, and pushes.

For the full internals — tag structure, wheel caching, version bumping — see the [guide](../../docs/guide.md).
