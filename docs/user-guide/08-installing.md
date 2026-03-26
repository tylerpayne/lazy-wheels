# Install Packages from GitHub Releases

uvr can install workspace packages directly from their GitHub releases, resolving internal dependencies automatically.

## Install from your own repo

From within the repository that published the releases:

```bash
uvr install my-package           # latest version
uvr install my-package@1.2.3     # pinned version
```

This walks the workspace dependency graph, downloads the appropriate wheel for each internal dependency, and installs them all with `uv pip install`. External (PyPI) dependencies are resolved by pip from wheel metadata.

## Install from another repo

```bash
uvr install acme/other-monorepo/my-package
uvr install acme/other-monorepo/my-package@1.2.3
```

Your `gh` CLI must be authenticated with access to the target repository.
