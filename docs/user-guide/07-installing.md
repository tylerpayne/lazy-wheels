# Installing & Downloading

## Install from GitHub releases

uvr can install workspace packages directly from their GitHub releases, resolving internal dependencies automatically.

```bash
uvr install my-package           # latest version (within your own repo)
uvr install my-package@1.2.3     # pinned version
```

This walks the workspace dependency graph, downloads the appropriate wheel for each internal dependency, and installs them all with `uv pip install`.

### Install from another repo

```bash
uvr install acme/other-monorepo/my-package
uvr install acme/other-monorepo/my-package@1.2.3
```

Your `gh` CLI must be authenticated with access to the target repository.

## Download wheels without installing

```bash
uvr download acme/repo/my-package              # latest release
uvr download acme/repo/my-package@1.2.3       # specific version
uvr download acme/repo/my-package --run-id ID  # from CI artifacts
```

Wheels are saved to `dist/` by default (override with `-o DIR`). Only platform-compatible wheels are downloaded.
