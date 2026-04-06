# uvr

[![Docs](https://github.com/tylerpayne/uvr/actions/workflows/docs.yml/badge.svg)](https://tylerpayne.github.io/uvr/)
[![PyPI](https://img.shields.io/pypi/v/uv-release)](https://pypi.org/project/uv-release/)

Footgun-free release management for [uv](https://github.com/astral-sh/uv) workspaces.

## Quick Start

```bash
pip install uv-release
uvr workflow init        # generate .github/workflows/release.yml
uvr release     # detect changes, show plan, dispatch to CI
```

## Releasing

```bash
# Preview what would be released
uvr release --dry-run

# Release to CI (default)
uvr release

# Release locally (pure-python packages only)
uvr release --where local
```

### Version bumping

```bash
uvr bump --minor             # bump changed packages to next minor
uvr bump --alpha             # enter alpha pre-release cycle
uvr bump --rc                # promote alpha → rc
uvr bump --stable            # exit pre-release → stable
uvr bump --packages my-pkg --patch  # bump specific package(s)
```

`uvr release` auto-detects from the version. It strips `.devN` and publishes whatever is underneath.

```bash
uvr release              # 1.0.1.dev0 → release 1.0.1
uvr release              # 1.0.1a0.dev0 → release 1.0.1a0
uvr release --dev        # publish 1.0.1.dev0 as-is
```

### Skipping and reusing

```bash
uvr release --skip uvr-build                       # skip the build job
uvr release --skip-to uvr-release                  # skip everything before release
uvr release --skip uvr-build --reuse-run 12345     # reuse artifacts from run 12345
```

## Managing runners

```bash
uvr workflow runners                                    # show all package runners
uvr workflow runners my-pkg --add macos-14 windows-latest  # add build runners
uvr workflow runners my-pkg --clear                     # reset to default (ubuntu-latest)
```

## Installing

```bash
uvr install --dist dist                    # from local build
uvr install myorg/myrepo/my-pkg            # from GitHub release
uvr install myorg/myrepo/my-pkg@1.2.3      # specific version
```

## Downloading wheels

```bash
uvr download myorg/myrepo/my-pkg                  # latest release
uvr download myorg/myrepo/my-pkg -o wheels/       # save to custom dir
uvr download myorg/myrepo/my-pkg --run-id 12345   # from CI artifacts
```

## Hooks

Customize the release pipeline with Python hooks. Subclass `ReleaseHook` and override the methods you need:

```python
from uv_release_monorepo import ReleaseHook, ReleasePlan

class Hook(ReleaseHook):
    def post_plan(self, plan: ReleasePlan) -> ReleasePlan:
        data = plan.model_dump()
        data["deploy_env"] = "staging"
        return ReleasePlan.model_validate(data)
```

Configure in `pyproject.toml`:

```toml
[tool.uvr.hooks]
file = "uvr_hooks.py"          # default class: Hook
# or: file = "path/to/file.py:MyHook"
```

Or just drop a `uvr_hooks.py` with a `Hook` class at the workspace root. It's discovered automatically.

**Hook points.** `pre_plan` / `post_plan` (local), `pre_build` / `post_build`, `pre_build_stage` / `post_build_stage`, `pre_build_package` / `post_build_package`, `pre_release` / `post_release`, `pre_publish` / `post_publish`, `pre_bump` / `post_bump` (CI).

## How it works

All intelligence lives in `uvr release` on your machine. The CLI scans your workspace, diffs against baseline tags, walks the dependency graph, pins internal dependencies, expands the build matrix, and assembles a single JSON plan. CI receives the plan and follows it mechanically. No decisions, no debugging.

```
your machine:  scan → diff → pin → plan → [confirm]
                                              │
CI:                                    validate → build → release → publish → bump
```

You debug locally with `--dry-run`. CI stays stable across repo changes. Plans are inspectable JSON. Add your own jobs to the workflow by editing the YAML directly.

## Documentation

- **[User Guide](docs/user-guide/).** Setup, releasing, hooks, PyPI, skip/reuse, package filtering.
- **[Under the Hood](docs/under-the-hood/architecture.md).** The plan+execute model, dependency pinning, layered builds, workflow design.

## Repository Structure

```
packages/
  uv-release/            # the CLI tool (pip install uv-release)
  pkg-alpha/             # test packages for the release pipeline
  pkg-beta/
  pkg-delta/
  pkg-gamma/
docs/
  user-guide/            # task-oriented guides
  under-the-hood/        # internals documentation
  adr/                   # architecture decision records
  CHANGELOG.md           # workspace changelog
```
