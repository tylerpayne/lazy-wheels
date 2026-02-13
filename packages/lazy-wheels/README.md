# lazy-wheels

Lazy monorepo wheel builder — only rebuilds what changed.

## Installation

```bash
pip install lazy-wheels
```

## Usage

```bash
# Initialize workflow in your repo
lazy-wheels init

# Trigger a release
lazy-wheels release
lazy-wheels release -r r1
lazy-wheels release --force-all
```

## How it works

1. Discovers all packages in your UV workspace
2. Detects which packages changed since their last release (using per-package git tags)
3. Fetches unchanged wheels from previous GitHub releases
4. Builds only the changed packages
5. Creates per-package version tags
6. Bumps versions for the next release
7. Publishes all wheels to GitHub Releases
