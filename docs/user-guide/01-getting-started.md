# Getting Started

## Install

```bash
pip install uv-release
```

## Prerequisites

<code class="brand-code">uvr</code> works with uv workspace monorepos. Your root `pyproject.toml` must define workspace members.

```toml
[tool.uv.workspace]
members = ["packages/*"]
```

You also need the [GitHub CLI](https://cli.github.com/) (`gh`) authenticated. <code class="brand-code">uvr</code> uses it to create releases, download artifacts, and dispatch workflows. It always prompts for confirmation before committing, pushing, or dispatching on your behalf.

## Scaffold the release workflow

```bash
uvr workflow init
```

This writes `.github/workflows/release.yml` from a bundled template. Commit and push it.

```bash
git add .github/workflows/release.yml
git commit -m "chore: add release workflow"
git push
```

### Validate and upgrade

```bash
uvr workflow validate             # check structure and frozen fields
uvr workflow validate --diff      # show diff against template
uvr workflow init --upgrade       # three-way merge template changes
uvr workflow init --upgrade --editor code  # resolve merge conflicts in your editor of choice
```

Custom jobs survive upgrades. The three-way merge preserves your additions while picking up template changes.

## Check workspace status

```bash
uvr status
```

```
Packages
--------
  STATUS     PACKAGE     VERSION       PREVIOUS  DIFF FROM                    CHANGES  COMMITS
  changed    pkg-alpha   0.2.0.dev0    0.1.0     pkg-alpha/v0.2.0.dev0-base   3        2
  unchanged  pkg-beta    0.1.1.dev0    0.1.0     pkg-beta/v0.1.1.dev0-base    -        -
```

## Your first release

You can also release interactively with the [Claude Code skill](03-claude.md).

Preview the plan without making changes.

```bash
uvr release --dry-run
```

When ready, release for real.

```bash
uvr release
```

This generates a release plan locally, commits release versions, pushes, and dispatches to GitHub Actions. CI then builds, creates GitHub releases with wheels, publishes to configured indexes, and bumps versions to the next `.dev0`.

## Next steps

To release a minor or major version instead of patch, bump first. See [Managing Versions](04-versions.md) for the full version lifecycle.

```bash
uvr bump --minor
uvr release
```
