# How It Works

## The release flow

```
your machine                          GitHub Actions
─────────────                         ──────────────
uvr release
  ├─ scan workspace
  ├─ diff each package vs dev tag
  ├─ walk dependency graph
  ├─ precompute release notes
  ├─ expand build matrix
  ├─ print human-readable summary
  └─ [confirm] dispatch plan ────────► release.yml receives plan
                                         ├─ [hook] pre-build
                                         ├─ build: per-runner, topo-ordered
                                         ├─ [hook] post-build
                                         ├─ [hook] pre-release
                                         ├─ release: one GitHub release
                                         │   per changed package
                                         ├─ finalize:
                                         │   ├─ bump patch versions
                                         │   ├─ commit & tag dev baselines
                                         │   └─ push
                                         └─ [hook] post-release
```

The workflow is a **pure executor**. It receives the plan as a single JSON input and follows it exactly. All intelligence — change detection, dependency resolution, matrix expansion, release notes — lives in the CLI on your machine.

## The plan

The `ReleasePlan` JSON encodes everything CI needs: `uvr_version`, `uvr_install`, `python_version`, `skip` (jobs to skip), `reuse_run_id`, changed/unchanged packages, build matrix, release matrix, and version bumps. CI never runs git commands or makes decisions.

## Version bumping

You control **major.minor** by editing `version` in each package's `pyproject.toml`. CI controls **patch** — after every release, it bumps the patch number and appends `.dev0`, commits, and tags the dev baseline. Between releases, your pyproject.toml always shows the development version (e.g., `0.5.2.dev0`). On release, the `.dev0` is stripped automatically.

## Dependency pinning

When a package depends on another workspace package, uvr pins the internal dependency constraint to the just-published version before releasing. This ensures that published wheels remain installable even when only a subset of packages change in the next cycle. Pin updates are detected during `uvr release` — if any pins need updating, uvr prompts you to write them and commit before dispatching.

## Tag structure

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

## The workflow model

`release.yml` is the source of truth for the workflow. The `ReleaseWorkflow` Pydantic model defines the expected schema -- all seven jobs with their default steps, `needs` chain, and `if` conditions. `uvr init` generates the initial YAML from the model's defaults. `uvr validate` checks an existing YAML against the model. Core jobs (build, release, finalize) have default steps that warn (but don't fail) if modified. Hook jobs accept any steps.
