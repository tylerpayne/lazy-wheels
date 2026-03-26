# uv-release-monorepo

Push-button releases for [uv](https://github.com/astral-sh/uv) monorepos. Rebuilds only what changed, creates one GitHub release per package, handles version bumping. You own major.minor; CI owns patch.

## Quick Start

```bash
# Install as a uv tool
uv tool install uv-release-monorepo
# Or via pip
# pip install uv-release-monorepo
# Or as uv dev dependency
# uv add --dev uv-release-monorepo
uvr init
uvr release
```

## What it does

`uvr release` scans your workspace, diffs each package against its last release, walks the dependency graph, builds a plan, and dispatches it to GitHub Actions. Seven jobs run in sequence:

```
pre-build -> build -> post-build -> pre-release -> publish -> finalize -> post-release
```

Hook jobs (pre-build, post-build, pre-release, post-release) are no-ops by default and auto-skipped. Edit `release.yml` directly to add your CI steps — tests, linting, PyPI publish, notifications.

## Key commands

```bash
uvr init                        # generate release.yml
uvr validate                    # check release.yml against the model
uvr release                     # detect changes, show plan, dispatch to CI
uvr release --where local       # build and publish locally
uvr release --dry-run           # preview without making changes
uvr release --dev               # publish a .devN release
uvr release --pre a             # publish an alpha pre-release
uvr release --rebuild-all       # rebuild everything
uvr runners my-pkg --add macos-14   # add a build runner
uvr status                      # show current config
uvr install my-pkg              # install from GitHub releases
```

## Documentation

- **[User Guide](../../docs/user-guide/README.md)** — task-oriented: how to set up, release, customize hooks, publish to PyPI, skip/reuse, filter packages
- **[Under the Hood](../../docs/under-the-hood/README.md)** — implementation details: change detection, dependency pinning, build matrix, workflow model, CI execution
