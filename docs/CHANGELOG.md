# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [v0.18.0b0] - 2026-03-29

### Changed
- **BREAKING**: Bump `ReleasePlan` schema version to 9 — consolidate per-package data into `ChangedPackage` model replacing `BumpPlan`, `MatrixEntry`, `PublishEntry`, `current_versions`, `release_tags`, and `bumps` fields
- **BREAKING**: Rename release pipeline phase from "publish" to "release" — affects `--skip` flag values, workflow job names, and plan field names (`publish_commands` → `release_commands`, `publish_matrix` → `release_matrix`, `runners` → `build_matrix`)
- **BREAKING**: Rename all shared module functions to verb-first convention — `load_pyproject` → `read_pyproject`, `save_pyproject` → `write_pyproject`, `step` → `print_step`, `fatal` → `exit_fatal`, `discover_packages` → `find_packages`, `get_baseline_tags` → `find_baseline_tags`, `base_version` → `get_base_version`, `get_uvr_config` → `get_config`, `get_uvr_matrix` → `get_matrix`
- **BREAKING**: Restructure `shared/` modules by topological dependency layer — `planner/` subpackage absorbs `versions.py`, `deps.py`, `graph.py`, `changes.py`; `context/` subpackage replaces `discovery.py` with `RepositoryContext` model; `execute.py` → `executor.py`
- Change `ReleasePlanner` to accept a pre-built `RepositoryContext` instead of calling discovery functions internally
- Change `uvr init --upgrade` to use editor prompt with `--wait` for GUI editors instead of `git checkout -p` for conflict resolution
- Prefix all core workflow jobs with `uvr-` (`uvr-validate`, `uvr-build`, `uvr-release`, `uvr-finalize`) to distinguish from user-defined jobs
- Replace GitHub API calls and tag scanning with O(1) local ref lookups via `find_previous_release` inverse version bump

### Added
- Add `RepositoryContext` model that pre-fetches all repository state (repo handle, git tags, GitHub releases, packages, release tags, baselines) in a single `build_context()` call
- Add `ChangedPackage` model extending `PackageInfo` with `current_version`, `release_version`, `next_version`, `last_release_tag`, `release_notes`, `make_latest`, and `runners` fields
- Add `get_path()` helper in `toml.py` for navigating nested TOML dicts without chained `.get()` calls
- Add `--editor` CLI flag and `[tool.uvr.config].editor` setting for configuring conflict resolution editor in `uvr init --upgrade`
- Add `@computed_field` properties on `ReleasePlan` for `build_matrix` and `release_matrix` — derived from `changed` packages, serialized into JSON for CI workflow consumption
- Add cumulative pre-release notes — beta notes include all commits since the last final release, not just since the last alpha
- Add `--full-release-notes` flag to show all commits (default truncates to 10 with overflow count)
- Add `is_pre()` helper for detecting alpha/beta/rc versions
- Add `--allow-dirty` flag to `uvr release` for running with uncommitted changes
- Add progress bar with per-phase timing and bar chart summary to `uvr release` planning output
- Add `find_previous_release()` inverse version bump — derives predecessor via O(1) ref lookups with kind chain fallback (rc → b → a → final)
- Add `uvr skill init --upgrade` with three-way merge and editor conflict resolution matching `uvr init --upgrade`
- Add versioned skill templates replacing git commit SHA tracking

### Removed
- Remove `BumpPlan`, `MatrixEntry`, `PublishEntry`, `PinChange`, `DepPinChange` models — data consolidated into `ChangedPackage`
- Remove `git()`, `gh()`, `run()` subprocess wrappers from `shell.py` — replaced by pygit2 and httpx in earlier versions
- Remove unused functions: `dev_number`, `is_final`, `is_prerelease`, `is_postrelease`, `tag_for_package`, `topo_sort`, `rewrite_pyproject`, `update_dep_pins`
- Remove GitHub API dependency for release detection — all tag lookups are now local via pygit2
- Remove `git/remote.py` module

### Fixed
- Fix `git merge-file` exit code check in `uvr init --upgrade` — was treating conflict count > 1 as fatal error instead of only negative exit codes
- Fix multiline `run:` steps in generated workflow YAML rendering as quoted strings instead of block scalars (`|`)
- Fix `strategy` field rendering after `steps` in workflow YAML job definitions
- Fix `--pre b` with alpha version producing another alpha instead of beta
- Fix `--dev` rejecting clean versions — now auto-appends `.dev0` consistent with other release types

## [v0.17.0] - 2026-03-27

### Added
- Add `pre_build_stage`/`post_build_stage` hooks called before and after each build stage with the list of packages
- Add `pre_build_package`/`post_build_package` hooks called around individual package builds (run in parallel threads)
- Add optional `runner` parameter to `pre_build`/`post_build` hooks identifying the active runner labels

### Changed
- **BREAKING**: Replace `BuildStage.commands` dict (with `__setup__`/`__cleanup__` sentinel keys) with explicit `setup`, `packages`, and `cleanup` fields
- **BREAKING**: Change `build_commands` dict keys from JSON-encoded strings to `RunnerKey` — a Pydantic-validated `tuple[str, ...]` that parses JSON strings at model validation time
- Change `ReleaseExecutor.build()` to accept `str | list[str] | None` for the runner parameter — JSON strings from CI are parsed via the `RunnerKey` validator instead of a separate `parse_runner` function

## [v0.16.0] - 2026-03-27

### Added
- Add `validate-plan` CI job that runs first in the release pipeline — validates the plan JSON as a `ReleasePlan` and pretty-prints it to stdout
- Add `uvr validate-plan` CLI subcommand for validating and displaying a release plan

### Changed
- Change pipeline order to `validate-plan → build → publish → finalize` — build now depends on validate-plan

## [v0.15.0] - 2026-03-27

### Added
- Add `ReleaseHook` plugin system for extending the release pipeline with Python hooks — supports local hooks (`pre_plan`/`post_plan`) and CI hooks (`pre_build`/`post_build`/`pre_release`/`post_release`/`pre_finalize`/`post_finalize`) (ADR-0011)
- Add `[tool.uvr.hooks]` config key and convention-based discovery (`uvr_hooks.py` at workspace root)
- Export `ReleaseHook` and `ReleasePlan` from `uv_release_monorepo` package root

### Changed
- Replace `git` and `gh` subprocess calls with pygit2 and httpx for faster release planning (ADR-0012)
- Change `uvr init --upgrade` to use three-way merge for combining template updates with user customizations (ADR-0013)
- Bump `ReleasePlan` schema version to 8 — plans now preserve extra keys injected by hooks

## [v0.14.3] - 2026-03-27

### Changed
- Deduplicate subprocess calls in the planning phase — fetch git tags and GitHub releases once instead of 3x and 2x respectively
- Batch per-package baseline tag lookups into a single `git tag --list` call with Python set filtering (eliminates N subprocess calls)
- Parallelize per-package `git diff` change detection with `ThreadPoolExecutor`
- Pre-compute release notes once instead of regenerating per caller

## [v0.14.2] - 2026-03-27

### Fixed
- Fix build commands failing on Windows runners — replace `mkdir -p` and `find -delete` with cross-platform `uv run python -c` equivalents (#9)

## [v0.14.1] - 2026-03-27

### Fixed
- Fix `uvr init --upgrade` step matching to use all of id/name/uses for cross-matching between old and new templates
- Fix `uvr init --upgrade` to block on uncommitted release.yml changes and handle quit gracefully
- Remove special characters from CLI output

## [v0.14.0] - 2026-03-27

### Added
- Add `uvr init --upgrade` to update frozen template fields in an existing `release.yml` while preserving custom jobs, triggers, and env vars
- Add `uvr skill init` to copy bundled Claude Code skills into your project

## [v0.13.4] - 2026-03-27

### Fixed
- Fix `uvr build`/`uvr finalize` failing on Windows runners — `--plan` now falls back to the `UVR_PLAN` environment variable and supports `@file` input (#8)

### Changed
- Change workflow template to omit `--plan "$UVR_PLAN"` from build/finalize run commands — re-run `uvr init` to update existing workflows

## [v0.13.3] - 2026-03-27

### Fixed
- Fix `uvr status` build display to show all packages built per runner, including transitive deps marked with `(dep)`

## [v0.13.2] - 2026-03-27

### Fixed
- Fix cross-runner builds failing when a workspace dependency is only assigned to a different runner — unchanged deps are now fetched into `deps/` and changed transitive deps are built on every runner that needs them (#7)

## [v0.13.1] - 2026-03-27

### Fixed
- Fix topo-sort not considering `[build-system].requires` dependencies, causing concurrent builds to fail when a package's build-time dep hadn't finished building (#6)

## [v0.13.0] - 2026-03-27

### Changed
- Move version setting and dependency pinning from CI build commands to local pre-dispatch — `uvr release` now commits release versions before dispatching to CI, so release tags point at commits with the correct version (ADR-0010)

## [v0.12.0] - 2026-03-27

### Changed
- Change `uvr release --json` to output only the plan JSON to stdout — no human-readable output, no worktree check, no dispatch prompt

## [v0.11.3] - 2026-03-27

### Fixed
- Fix layered builds resolving workspace sources instead of pre-built wheels — `uv build` now passes `--no-sources` for layer 1+ packages (#5)

## [v0.11.2] - 2026-03-27

### Changed
- Change `uvr runners` to group output by runner instead of by package and show the default (`ubuntu-latest`) for unconfigured packages

## [v0.11.1] - 2026-03-27

### Fixed
- Fix `uvr release` CI dispatch checking out the default branch instead of the dispatching branch

## [v0.11.0] - 2026-03-27

### Changed
- Move dependency pin writes from local two-pass flow to inline `uvr pin-deps` commands in the build plan (ADR-0009) — pins are only applied if the build succeeds

### Fixed
- Fix `set_version` and `pin_dependencies` crashing on pyproject.toml files without a `[project]` table

## [v0.10.0] - 2026-03-27

### Added
- Add parallel builds within runners — packages at the same dependency depth build concurrently using topological layers

## [v0.9.0] - 2026-03-27

### Added
- Add self-hosted runner support — runners are now label sets (e.g. `uvr runners pkg --add "self-hosted,linux,x64"`)
- Add tag and release conflict detection — planner validates no planned tags/releases already exist before dispatching
- Add `--where local` platform check — errors when changed packages have runners for a different OS
- Add HEAD-vs-remote sync check before CI dispatch

### Changed
- **BREAKING**: Remove hook jobs from workflow model — `uvr init` generates only `build`, `release`, `finalize`; users add their own jobs by editing `release.yml`
- **BREAKING**: Remove `uvr set-version` subcommand — planner emits `uv version` commands instead
- **BREAKING**: Change runner type from `str` to `list[str]` in `MatrixEntry`, `ReleasePlan`, and `[tool.uvr.matrix]`
- **BREAKING**: Require `org/repo/pkg` format for `uvr install` (bare package names no longer accepted)
- Change `uvr status` to an alias for `uvr release --dry-run`
- Improve dry-run output: column headers, current → release version display, version rewrite visibility in build section
- Rewrite README with usage-focused sections

### Removed
- Remove `uvr set-version` subcommand (use `uv version` directly)
- Remove hook job classes (`HookJob`, `PreBuildJob`, `PostBuildJob`, `PreReleaseJob`, `PostReleaseJob`)
- Remove `_NOOP_STEPS` constant and auto-skip logic for no-op hooks

### Fixed
- Fix publish workflow `files:` pattern missing `dist/` prefix — wheels not attached to GitHub releases
- Fix conflict error suggesting deletion as first option — now shows `--post` and version bump first

## [v0.8.0] - 2026-03-26

### Added
- Add `--dev`, `--pre {a,b,rc}`, and `--post` flags to `uvr release` for PEP 440 dev, pre, and post releases (ADR-0008)
- Add `uvr build`, `uvr finalize`, `uvr set-version`, and `uvr pin-deps` subcommands (previously separate `uvr-ci` entry point)
- Add `--where {ci,local}` flag to `uvr release` — replaces the separate `uvr run` command
- Add `--dry-run` flag to `uvr release` for previewing the release plan without changes
- Add `PlanCommand` model for pre-computed shell commands in the release plan
- Add `ReleasePlanner` class as the single entry point for creating release plans

### Changed
- **BREAKING**: Remove `uvr run` command — use `uvr release --where local` instead
- **BREAKING**: Remove `uvr-ci` / `uvr-steps` entry point — all subcommands are now under `uvr`
- **BREAKING**: Rename CI subcommand `build-all` to `build`
- **BREAKING**: Bump `ReleasePlan` schema version to 6 — plans include pre-computed command sequences
- Change `ReleaseExecutor` to a pure command runner — all domain logic moved to `ReleasePlanner`
- Change `find_release_tags` to query GitHub releases instead of git tags
- Change release tag lookup to only match versions below the current base version
- Change `BumpPlan.new_version` to store the exact pyproject.toml version (includes `.dev0` suffix)
- Improve `uvr --help` with grouped command listing (Commands, CI steps, Low-level)
- Improve `uvr release --help` with argument groups (mode, build, dispatch, local, output)
- Column-align package, build, and finalize sections in dry-run output

### Removed
- Remove `pipeline/` re-export package — all imports use `shared.*` directly
- Remove `ci/` package — step functions inlined into CLI
- Remove `run_release()`, `execute_plan()`, `bump_versions()`, `collect_published_state()` functions
- Remove legacy `-dev` baseline tag handling

### Fixed
- Fix `--dry-run` not showing auto-skipped no-op hook jobs
- Fix `--dev` release silently publishing a clean version when pyproject.toml has no `.dev` suffix
- Fix double `.dev0.dev0` in post-release bump versions
- Fix pre-release bump producing a patch bump instead of next pre-release `.dev0` (e.g. `a0` → `a1.dev0`)
- Fix post-release bump producing `.post0.dev0` instead of `.post1.dev0`

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
