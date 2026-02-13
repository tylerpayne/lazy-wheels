# lazy-wheels

Lazy monorepo wheel builder — only rebuilds what changed.

Designed for [uv](https://github.com/astral-sh/uv) workspaces. Detects
which packages changed since the last release, propagates through the
dependency DAG, builds only what's needed, and creates a GitHub release
with the full set of wheels.

## Install

```bash
pip install lazy-wheels
# or
uv tool install lazy-wheels
```

## Quick start

```bash
cd your-monorepo
lazy-wheels init      # scaffolds .github/workflows/release.yml
git add .github && git commit -m "add release workflow" && git push
gh workflow run release.yml
```

## What it does

```
discover packages  →  find last tag  →  diff + propagate DAG
    →  fetch unchanged wheels from previous release
    →  uv build changed packages
    →  git tag (on the built commit)
    →  bump patch versions + commit
    →  gh release create (on the pre-bump tag)
```

## CLI

```
lazy-wheels init [--workflow-dir DIR]    Scaffold the GitHub Actions workflow
lazy-wheels release [--force-all]       Run the release pipeline
```

## Versioning policy

Humans own `major.minor` in each package's `pyproject.toml`. CI
auto-increments `patch` after each release. Internal workspace
dependencies are exact-pinned (`==x.y.z`).

## Requirements

- A uv workspace with `[tool.uv.workspace] members` in the root `pyproject.toml`
- `uv` and `gh` (GitHub CLI) available on PATH (both are pre-installed on GitHub Actions runners)

## Dependency graph

The DAG is built from `[project].dependencies`,
`[project.optional-dependencies]`, and `[dependency-groups]` (PEP 735).
Extras on dependency specifiers (e.g. `my-utils[full]==1.0.0`) are
preserved through version bumps.

## How TOML rewriting works

Uses [tomlkit](https://github.com/sdispater/tomlkit) for
format-preserving edits — comments, ordering, and whitespace are
untouched. Dependency specifiers are parsed with
[packaging](https://packaging.pypa.io/), so extras, markers, and
complex specifiers are handled correctly.
