## IMPORTANT: After ANY Code Change

```bash
uv run poe fix     # auto-fix formatting + lint
uv run poe check   # verify lint + types
```

Run `fix` then `check` after every change. Do not skip this. Do not commit without passing `check`.

## Structure

uv workspace monorepo. All packages live in `packages/`. Package filtering for releases is controlled by `[tool.uvr.config]` include/exclude in the root `pyproject.toml`.

- `uv-release-monorepo` — the CLI tool (published to PyPI as `uvr`)
- `pkg-alpha`, `pkg-beta`, `pkg-delta`, `pkg-gamma` — test packages for the release pipeline

## Commands

```bash
uv sync                    # Install all deps
uv run poe fix             # lintfix + format
uv run poe check           # lint + typecheck
uv run poe test            # Run tests
uv run poe all             # fix + check + test
uvr status                 # Show release status and changed packages
uvr release                # Generate plan, prompt, dispatch to GitHub Actions
```

## Before Implementing a Feature

Before starting work on a new feature, consider whether the decision qualifies as an ADR —
meaning it is hard or costly to reverse, constrains future choices, or would confuse a new
team member. This applies at both the workspace level (tooling, CI, cross-cutting conventions)
and the package level (API design, dependencies, internal architecture). If it might qualify,
ask the user whether to document it with `/adr` before writing code.

## Key Conventions

- Python >=3.11. Ruff + ty config in root `pyproject.toml`.
- Single changelog at `docs/CHANGELOG.md` using [Keep a Changelog](https://keepachangelog.com/). ADRs use MADR format in `docs/adr/`.
- Version management: you own major.minor (`uv version --bump minor --directory packages/<pkg>`). CI owns patch.
- Release process: see `/release` skill. Tag format: `{pkg}/v{version}` (release), `{pkg}/v{version}-dev` (dev baseline).
- `uv-release-monorepo` also publishes to PyPI via `.github/workflows/publish.yml`.
