# Build Locally

Build changed packages on your machine without publishing.

```bash
uvr build
```

This runs the same layered dependency ordering as CI but outputs wheels to `dist/`. Useful for testing builds before releasing.

## Rebuild everything

```bash
uvr build --rebuild-all
```

Ignores change detection and builds every package.

## Pin a Python version

```bash
uvr build --python 3.11
```

Defaults to `3.12`.

## Install from a local build

After building, install wheels directly from `dist/`:

```bash
uvr install --dist dist                    # install all wheels
uvr install --dist dist my-package         # install a specific package
```

---

**Under the hood:** [Build matrix internals](../under-the-hood/04-build-matrix.md)
