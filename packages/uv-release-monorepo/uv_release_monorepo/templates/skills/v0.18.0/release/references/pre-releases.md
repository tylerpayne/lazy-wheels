# Pre-releases

Pre-releases let you publish alpha, beta, or release candidate versions for testing before a final release. They follow [PEP 440](https://peps.python.org/pep-0440/#pre-releases) versioning.

## Usage

```bash
uvr release --pre a     # alpha   → 1.2.3a0
uvr release --pre b     # beta    → 1.2.3b0
uvr release --pre rc    # release candidate → 1.2.3rc0
```

## How it works

1. uvr strips the `.devN` suffix from each changed package's version to get the base `X.Y.Z`
2. It scans existing git tags to find the next available pre-release number for that kind
3. The published version becomes `X.Y.Za0` (or `b0`, `rc0`, etc.)
4. After release, the pyproject.toml version is bumped to `X.Y.Za1.dev0` (dev toward the next pre-release of the same kind)

## Version ordering

Pre-releases sort before the final release:

```
1.0.1.dev0 < 1.0.1a0 < 1.0.1a1 < 1.0.1b0 < 1.0.1rc0 < 1.0.1
```

## Auto-incrementing

The pre-release number auto-increments by scanning existing tags. If `my-pkg/v1.0.1a0` already exists, the next `--pre a` release will produce `1.0.1a1`.

## Example workflow

```bash
# First alpha
uvr release --pre a
# → publishes my-pkg 1.2.3a0
# → bumps pyproject.toml to 1.2.3a1.dev0

# Second alpha (after more changes)
uvr release --pre a
# → publishes my-pkg 1.2.3a1
# → bumps pyproject.toml to 1.2.3a2.dev0

# Release candidate
uvr release --pre rc
# → publishes my-pkg 1.2.3rc0

# Final release
uvr release
# → publishes my-pkg 1.2.3
# → bumps pyproject.toml to 1.2.4.dev0
```

## Merging

**Do not merge after each pre-release.** The typical pre-release workflow is multiple releases from the same branch (alpha → beta → rc → final). Stay on the branch through the entire cycle and merge only after the final release.

After `--pre a`, finalize bumps the pyproject.toml version to something like `1.2.3a1.dev0`. If you merged that to main, main's version would be an intermediate pre-release dev version — confusing and unnecessary.

Instead, keep iterating on the branch until you're ready for the final release. A final `uvr release` automatically strips all suffixes (dev, pre, post) to produce a clean `X.Y.Z`:

```bash
uvr release --pre a      # 1.2.3a0 — stay on branch
uvr release --pre rc     # 1.2.3rc0 — stay on branch
uvr release              # 1.2.3 — now merge to main
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
