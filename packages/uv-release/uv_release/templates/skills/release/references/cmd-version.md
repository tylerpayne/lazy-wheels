# `uvr version`

Read, set, or bump package versions. With no flags, displays current versions.

```bash
uvr version                                    # show versions
uvr version --bump                             # increment the last version section
uvr version --bump minor                       # bump all changed packages to next minor
uvr version --packages foo --bump patch        # bump one package
uvr version --bump stable                      # strip pre/dev suffixes
uvr version --set 2.0.0                        # set an explicit version
```

## Modes

Exactly one mode flag is accepted. If none is given, versions are displayed (read-only).

### `--bump [AXIS]`

Increments a version number. With no argument, auto-detects the last section and increments it.

| Flag | Effect |
|------|--------|
| `--bump` | Auto-detect and increment the last section (dev, pre-release, post, or patch) |
| `--bump dev` | Increment the dev number |
| `--bump patch` | Next patch, dev track (`1.2.3.dev0` to `1.2.4.dev0`) |
| `--bump minor` | Next minor, dev track (`1.2.3.dev0` to `1.3.0.dev0`) |
| `--bump major` | Next major, dev track (`1.2.3.dev0` to `2.0.0.dev0`) |
| `--bump post` | Enter or advance post-release track (`1.2.3` to `1.2.3.post0.dev0`) |
| `--bump stable` | Strip pre-release and dev suffixes for a clean version |

### `--set VERSION`

Sets all targeted packages to the given version string.

## Scope flags

| Flag | Description |
|------|-------------|
| `--all-packages` | Target all workspace packages |
| `--packages PKG [...]` | Target only the named packages |
| `--not-packages PKG [...]` | Exclude specific packages |
| `--force` | Target unchanged packages (implies `--all-packages`) |

## Options

| Flag | Description |
|------|-------------|
| `--no-pin` | Skip internal dependency pinning |
| `--no-commit` | Skip git commit |
| `--no-push` | Skip git push |

## What it does

1. Computes the new version for each target package
2. Writes the new version to each package's `pyproject.toml`
3. Pins internal dependency lower bounds to match the new versions
4. Runs `uv sync` to update the lockfile
5. Commits all changes

## Common patterns

```bash
# Read current versions
uvr version

# Prepare a minor release for changed packages
uvr version --bump minor

# Strip a dev suffix to publish a stable version
uvr version --bump stable

# Set an explicit version
uvr version --set 2.0.0
```

See `post-releases.md` for post-release bumps.
