# uv-release-monorepo

The missing CI release orchestrator for [uv](https://github.com/astral-sh/uv) workspaces. Rebuilds only what changed, creates one GitHub release per package, handles version bumping.

## Quick Start

```bash
uv tool install uv-release-monorepo
uvr init        # generate .github/workflows/release.yml
uvr release     # detect changes, show plan, dispatch to CI
```

## Releasing

```bash
# Preview what would be released
uvr status

# Release to CI (default)
uvr release

# Release locally (pure-python packages only)
uvr release --where local
```

### Version bumping

```bash
uvr bump --all --minor       # 1.0.1.dev0 → 1.1.0.dev0
uvr bump --all --alpha       # 1.0.1.dev0 → 1.0.1a0.dev0
uvr bump --all --rc          # 1.0.1a2.dev0 → 1.0.1rc0.dev0
uvr bump --package my-pkg --patch  # bump one package
```

`uvr release` auto-detects from the version — just strip `.devN` and publish:

```bash
uvr release              # 1.0.1.dev0 → release 1.0.1
uvr release              # 1.0.1a0.dev0 → release 1.0.1a0
uvr release --dev        # publish 1.0.1.dev0 as-is
```

### Skipping and reusing

```bash
uvr release --skip build                      # skip the build job
uvr release --skip-to release                 # skip everything before release
uvr release --skip build --reuse-run 12345    # reuse artifacts from run 12345
```

## Managing runners

```bash
uvr runners                        # show all package runners
uvr runners my-pkg --add macos-14  # add a build runner
uvr runners my-pkg --clear         # reset to default (ubuntu-latest)
```

## Installing from releases

```bash
uvr install myorg/myrepo/my-pkg           # latest release
uvr install myorg/myrepo/my-pkg@1.2.3     # specific version
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

Or just drop a `uvr_hooks.py` with a `Hook` class at the workspace root — it's discovered automatically.

**Hook points:** `pre_plan` / `post_plan` (local), `pre_build` / `post_build`, `pre_build_stage` / `post_build_stage`, `pre_build_package` / `post_build_package`, `pre_release` / `post_release`, `pre_finalize` / `post_finalize` (CI).

## How it works

`uvr release` scans your workspace, diffs each package against its last baseline tag, walks the dependency graph, and builds a plan containing every shell command needed for the release. It dispatches this plan to GitHub Actions, which runs eight jobs:

```
validate-plan → build → release → finalize
```

Hook jobs (pre-build, post-build, pre-release, post-release) are no-ops by default — edit `release.yml` directly to add tests, linting, PyPI publish, or notifications.

## Documentation

- **[User Guide](../../docs/user-guide/README.md)** — setup, releasing, hooks, PyPI, skip/reuse, package filtering
- **[Under the Hood](../../docs/under-the-hood/README.md)** — change detection, dependency pinning, build matrix, workflow model
