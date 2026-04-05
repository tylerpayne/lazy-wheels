# uv-release-monorepo

Release management for [uv](https://github.com/astral-sh/uv) workspaces. Bump, build, and release only what changed. You manage major/minor versions, uvr manages the rest.

## Quick Start

```bash
uv add --dev uv-release-monorepo
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
uvr bump --all --alpha       # enter alpha cycle for all packages
uvr bump --all --rc          # promote alpha → rc
uvr bump --all --stable      # exit pre-release → stable
uvr bump --packages my-pkg --patch  # bump specific package(s)
```

`uvr release` auto-detects from the version — just strip `.devN` and publish:

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

Or just drop a `uvr_hooks.py` with a `Hook` class at the workspace root — it's discovered automatically.

**Hook points:** `pre_plan` / `post_plan` (local), `pre_build` / `post_build`, `pre_build_stage` / `post_build_stage`, `pre_build_package` / `post_build_package`, `pre_release` / `post_release`, `pre_bump` / `post_bump` (CI).

## How it works

`uvr release` scans your workspace, diffs each package against its last baseline tag, walks the dependency graph, and builds a plan containing every shell command needed for the release. It dispatches this plan to GitHub Actions, which runs eight jobs:

```
validate → build → release → bump
```

Hook jobs (pre-build, post-build, pre-release, post-release) are no-ops by default — edit `release.yml` directly to add tests, linting, PyPI publish, or notifications. Release assets are uploaded via `gh release create`.

## Documentation

- **[User Guide](../../docs/user-guide/index.md)** — setup, releasing, hooks, PyPI, skip/reuse, package filtering
- **[Under the Hood](../../docs/under-the-hood/index.md)** — change detection, dependency pinning, build matrix, workflow model
