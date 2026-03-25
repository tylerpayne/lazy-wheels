# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [v0.6.1] - 2026-03-25

### Added
- Add `--skip JOB` and `--skip-to JOB` flags to `uvr release` for skipping individual or ranges of jobs in the pipeline
- Add `--reuse-run RUN_ID` and `--reuse-release` flags for reusing build artifacts from a previous workflow run or existing GitHub releases
- Add `skip` and `reuse_run_id` workflow dispatch inputs with per-job `if:` conditions
- Add `JOB_ORDER` constant defining the canonical pipeline job ordering

### Fixed
- Fix `GH_TOKEN` not being set in post-release download step
- Fix duplicate `if:` keys in generated workflow when hook jobs had template-generated skip conditions

## [v0.6.0] - 2026-03-25

### Added
- Add `uvr workflow` command for reading, writing, and deleting any key in `release.yml` with `--set`, `--add`, `--insert --at`, `--remove`, and `--clear` flags
- Add `uvr runners PKG --add/--remove/--clear RUNNER` command for managing per-package build runners
- Add `ReleaseWorkflow` Pydantic model validating the full workflow YAML schema before writes
- Add `ruamel-yaml` dependency for lossless YAML round-tripping (preserves key order, comments, quote style)

### Changed
- **BREAKING**: Remove `-m`/`--matrix` flag from `uvr init` — use `uvr runners` instead
- **BREAKING**: Replace `uvr hooks PHASE {add|insert|remove|update|clear}` positional subcommands with flag-based `--add`/`--insert --at`/`--set`/`--remove`/`--clear`
- Split monolithic `cli.py` (1461 lines) into `cli/` package with one module per command

### Fixed
- Fix `on:` key being serialized as `true:` after YAML round-trip (PyYAML boolean coercion)
- Fix PyYAML corrupting GitHub Actions `${{ }}` expressions with double-quoted single quotes
- Fix PyYAML reordering top-level YAML keys on write

## [v0.5.0] - 2026-03-25

### Added
- Add per-runner build matrix where each runner builds all assigned packages in dependency order via `uvr-steps build-all`
- Add `topo_layers()` for computing dependency depth in the package graph
- Add `runners` and `dist_name` fields to `ReleasePlan` (schema version 4)

### Changed
- **BREAKING**: Replace per-package parallel matrix with per-runner matrix — fixes build failures when packages have build-time dependencies on sibling workspace packages
- **BREAKING**: Rename `--force-all` to `--rebuild-all`
- Publish job filters wheels by `dist_name` for per-package GitHub releases

### Fixed
- Fix CI dispatch pinning `uvr_version` to a `.dev` version that doesn't exist on PyPI
- Fix shell quoting issues with plan JSON by passing it via environment variable

## [v0.4.2] - 2026-03-23

### Added
- Add tag-triggered PyPI publish workflow (`uv-release-monorepo/v*` tags, excluding `-dev`)
- Add `make_latest` field to `PublishEntry`, driven by `[tool.uvr.config] latest` setting

### Fixed
- Fix glob wildcard for tag pattern in publish workflow trigger

## [v0.4.1] - 2026-03-23

### Fixed
- Fix PyPI publish rebuilding from HEAD (which picked up the `.dev0` bump) — now downloads the wheel directly from the GitHub release artifact

## [v0.4.0] - 2026-03-23

### Added
- Add `[tool.uvr.config]` with `include` and `exclude` lists for package filtering
- Add `--yes`/`-y` flag to skip the confirmation prompt

### Changed
- **BREAKING**: `uvr release` now prints the plan and prompts before dispatching — read-only by default (replaces `--dry-run`)
- **BREAKING**: Remove `--dry-run` flag from `uvr release`
- Replace shell scripts in release workflow with real GitHub Actions (`softprops/action-gh-release`)
- Move dependency pinning from CI to local planning — `build_plan()` pre-computes all version bumps, CI applies them via `apply_bumps()`
- Add `BumpPlan` model and `bumps` field to `ReleasePlan`
- Add precomputed release notes via `PublishEntry` and `generate_release_notes()`
- Bump `ReleasePlan` schema version to 3

## [v0.3.1] - 2026-03-20

### Fixed
- Fix dogfood release by using `uv run uvr-steps` from workspace instead of global install

## [v0.3.0] - 2026-03-20

### Added
- Plan+execute architecture: `uvr release` builds a `ReleasePlan` locally and dispatches it to CI as a pure executor
- Per-package GitHub releases tagged `{package}/v{version}`
- `uvr install PACKAGE[@VERSION]` with transitive internal dependency resolution
- `uvr install ORG/REPO/PACKAGE[@VERSION]` for remote installs
- `--python VERSION` flag to pin CI Python version (default 3.12)
- `uvr-steps` CLI entry point for workflow step dispatch
- `uvr status` command showing workflow config and changed packages

### Changed
- **BREAKING**: Replace `lazy-wheels` package entirely with `uv-release-monorepo`
- Matrix config moved to `[tool.uvr.matrix]` in workspace root `pyproject.toml`

### Removed
- Remove `lazy-wheels` package and all associated code
