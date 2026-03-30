# Pre-releases

Pre-releases let you publish alpha, beta, or release candidate versions for testing before a final release. They follow [PEP 440](https://peps.python.org/pep-0440/#pre-releases) versioning.

## Usage

Use `uvr bump` to enter a pre-release cycle, then `uvr release` to publish:

```bash
uvr bump --all --alpha       # enter alpha cycle → 1.2.3a0.dev0
uvr release                  # publishes 1.2.3a0, bumps to 1.2.3a1.dev0
```

## How it works

1. `uvr bump --alpha` (or `--beta`, `--rc`) sets each package's version to `X.Y.Za0.dev0`
2. `uvr release` strips `.devN` and publishes `X.Y.Za0`
3. After release, the pyproject.toml version is bumped to `X.Y.Za1.dev0` (dev toward the next pre-release of the same kind)
4. Subsequent `uvr release` calls publish `X.Y.Za1`, `X.Y.Za2`, etc.

To advance to the next kind (alpha → beta → rc), bump again:

```bash
uvr bump --all --beta        # advance to beta → 1.2.3b0.dev0
uvr release                  # publishes 1.2.3b0
```

## Version ordering

Pre-releases sort before the final release:

```
1.0.1.dev0 < 1.0.1a0 < 1.0.1a1 < 1.0.1b0 < 1.0.1rc0 < 1.0.1
```

## Example workflow

```bash
# Enter alpha cycle
uvr bump --all --alpha
# pyproject.toml: 1.2.3a0.dev0

uvr release
# → publishes 1.2.3a0
# → bumps to 1.2.3a1.dev0

# Second alpha (after more changes)
uvr release
# → publishes 1.2.3a1
# → bumps to 1.2.3a2.dev0

# Advance to release candidate
uvr bump --all --rc
# pyproject.toml: 1.2.3rc0.dev0

uvr release
# → publishes 1.2.3rc0

# Final release
uvr bump --all --patch
# pyproject.toml: 1.2.4.dev0

uvr release
# → publishes 1.2.4
# → bumps to 1.2.5.dev0
```

## Kind advancement rules

`uvr bump` enforces that pre-release kinds only move forward:

| Current | Allowed | Blocked |
|---|---|---|
| alpha | `--alpha`, `--beta`, `--rc` | — |
| beta | `--beta`, `--rc` | `--alpha` (downgrade) |
| rc | `--rc` | `--alpha`, `--beta` (downgrade) |

## Merging

**Do not merge after each pre-release.** The typical pre-release workflow is multiple releases from the same branch (alpha → beta → rc → final). Stay on the branch through the entire cycle and merge only after the final release.

After a pre-release, finalize bumps the pyproject.toml version to something like `1.2.3a1.dev0`. If you merged that to main, main's version would be an intermediate pre-release dev version — confusing and unnecessary.

Instead, keep iterating on the branch until you're ready for the final release:

```bash
uvr bump --all --alpha && uvr release   # 1.2.3a0 — stay on branch
uvr bump --all --rc && uvr release      # 1.2.3rc0 — stay on branch
uvr bump --all --patch && uvr release   # 1.2.4 — now merge to main
```

Merge to main only after the final release:

```bash
git checkout main
git pull --rebase
git merge --no-ff release/v1.2.3 -m "Merge release branch"
git push
```

## Tag format

Pre-release tags follow the same pattern as final releases:

```
my-pkg/v1.2.3a0
my-pkg/v1.2.3rc1
```
