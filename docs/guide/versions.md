# Managing Versions

## How versions work

Every package carries a [`.devN`](https://peps.python.org/pep-0440/#developmental-releases) suffix between releases. `uvr release` strips `.devN` to produce the published version. After release, CI bumps to the next patch `.dev0`.

```
1.3.0.dev0  →  release  →  1.3.0  →  CI bumps  →  1.3.1.dev0
```

## Bump changed packages

```bash
uvr version --bump minor
```

By default, `uvr version` only targets packages with changes since their last release. It writes new versions to `pyproject.toml`, updates internal dependency pins in downstream packages, and syncs the lockfile.

## Bump specific packages

```bash
uvr version --packages pkg-alpha pkg-beta --bump major
```

If other packages also have unreleased changes, `uvr` errors to prevent accidental partial bumps. Override with `--force`.

```bash
uvr version --packages pkg-alpha --bump major --force
```

## Bump

`--bump` increments a section of the version.

| Flag | Example | Description |
|---|---|---|
| `--bump` | `1.3.0.dev0` → `1.3.0.dev1` | Increment the last section (auto-detect) |
| `--bump` | `1.3.0a2` → `1.3.0a3` | Increment the last section (auto-detect) |
| `--bump` | `1.2.3` → `1.2.4` | Increment the last section (auto-detect) |
| `--bump major` | `1.2.3.dev0` → `2.0.0.dev0` | Next major version |
| `--bump minor` | `1.2.3.dev0` → `1.3.0.dev0` | Next minor version |
| `--bump patch` | `1.2.3.dev0` → `1.2.4.dev0` | Next patch version |
| `--bump dev` | `1.3.0.dev0` → `1.3.0.dev1` | Increment the dev number |
| `--bump post` | `1.2.3` → `1.2.3.post0.dev0` | Enter [post-release](https://peps.python.org/pep-0440/#post-releases) cycle |
| `--bump alpha` (alias `a`) | `1.3.0` → `1.3.0a0.dev0` | Enter or advance alpha cycle |
| `--bump beta` (alias `b`) | `1.3.0a3` → `1.3.0b0.dev0` | Advance to beta (resets pre-number) |
| `--bump rc` | `1.3.0b1` → `1.3.0rc0.dev0` | Advance to rc (resets pre-number) |
| `--bump stable` | `1.3.0a2.dev0` → `1.3.0` | Strip pre-release and dev suffixes |

With no argument, `--bump` detects the last section of the version and increments it. If the version ends in `.devN`, it bumps dev. If it ends in a pre-release like `a2`, it bumps the pre-release number. Otherwise it bumps patch.

## Skip dependency pinning

```bash
uvr version --packages pkg-alpha --bump minor --no-pin
```

By default, bumping a package updates `>=` pins in downstream dependents. The `--no-pin` flag skips this.

## How dependency pinning works

The planner builds a `published_versions` map for every workspace package.

- **Changed packages** publish at their release version. `0.1.5.dev0` strips to `0.1.5`.
- **Unchanged packages** use the version from their last release tag. `pkg-alpha/v0.1.4` gives `0.1.4`.

Every internal dep constraint is rewritten to `>=published_version`. Pins cover `[project].dependencies` and `[build-system].requires`.

```
pkg-beta/pyproject.toml
  pkg-alpha>=0.1.0  →  pkg-alpha>=0.1.5,<0.2.0

pkg-gamma/pyproject.toml
  pkg-beta>=0.1.0   →  pkg-beta>=0.2.0,<0.3.0

pkg-delta/pyproject.toml
  pkg-alpha>=0.1.0  →  pkg-alpha>=0.1.5,<0.2.0
```

After CI builds and publishes, the bump phase pins internal deps to the just-published versions. This ensures `pyproject.toml` constraints stay satisfiable during development.

Pin detection is pure. No files are modified during plan generation. If pins need updating, `uvr release` shows the pending changes before any writes happen.

## Pre-release workflow

```bash
uvr version --bump minor          # 1.3.0.dev0
uvr version --bump alpha          # 1.3.0a0.dev0 (enter alpha cycle)
uvr release                       # publishes 1.3.0a0, CI bumps to 1.3.0a1.dev0
uvr version --bump                # 1.3.0a2.dev0 (increment dev)
uvr release                       # publishes 1.3.0a2, CI bumps to 1.3.0a3.dev0
uvr version --bump beta           # 1.3.0b0.dev0 (advance to beta)
uvr release                       # publishes 1.3.0b0, CI bumps to 1.3.0b1.dev0
uvr version --bump rc             # 1.3.0rc0.dev0 (advance to rc)
uvr release                       # publishes 1.3.0rc0, CI bumps to 1.3.0rc1.dev0
uvr version --bump stable         # 1.3.0
uvr release                       # publishes 1.3.0, CI bumps to 1.3.1.dev0
```

Regressions (`rc` to `alpha`) and bumping a pre-release from a post-release are rejected. Use `--set <version>` if you really need to start over from an unusual state.

## Post-release workflow

```bash
uvr version --bump post           # 1.2.3 → 1.2.3.post0.dev0
uvr release                       # publishes 1.2.3.post0, CI bumps to 1.2.3.post1.dev0
```

Post-release bumps start from a clean version that has already been published. They are useful for metadata-only fixes or rebuild-and-republish scenarios.

## Dev release workflow

```bash
uvr release --dev                 # publishes 1.3.0.dev0 as-is
```

Dev releases publish the current `.devN` version without stripping the suffix. This is useful for testing packages from an index before committing to a real release.

## Tag formats

`uvr` creates two kinds of tags.

**Release tags** mark published versions. Format is `{package}/v{version}`. These are created during the release phase.

```
pkg-alpha/v1.3.0
```

**Baseline tags** mark where the next dev cycle begins. Format is `{package}/v{version}-base`. These are created during the bump phase. Change detection compares HEAD against the baseline tag. If no baseline exists, the package is treated as new.

```
pkg-alpha/v1.3.1.dev0-base
```

The full version lifecycle looks like this.

```
commit A  ← pkg-alpha/v0.1.5              (release tag)
commit B  ← pkg-alpha/v0.1.6.dev0-base    (baseline tag, pyproject.toml bumped to 0.1.6.dev0)
commits   … normal development …
commit C  ← pkg-alpha/v0.1.6              (release tag)
commit D  ← pkg-alpha/v0.1.7.dev0-base    (baseline tag, pyproject.toml bumped to 0.1.7.dev0)
```

For more on how baseline tags drive change detection, see [Change Detection](../internals/change-detection.md).
