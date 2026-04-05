# Bump Versions

Use `uvr bump` to prepare the next version. You own major, minor, and pre-release transitions — CI handles patch bumps after each release.

By default, `uvr bump` only bumps packages with changes since the last release.

## Bump changed packages

```bash
uvr bump --minor                 # bump changed packages to next minor
uvr bump --major                 # bump changed packages to next major
uvr bump --patch                 # bump changed packages to next patch
```

## Bump all packages

```bash
uvr bump --all --minor
```

## Bump specific packages

```bash
uvr bump --packages my-pkg other-pkg --minor
```

Fails if other packages also have unreleased changes — use `--force` to skip this check.

## Skip dependency pinning

By default, bumping a package also updates `>=` pins in downstream consumers. Use `--no-pin` to bump the version without touching dependents:

```bash
uvr bump --packages my-pkg --minor --no-pin
```

## Pre-release cycles

```bash
uvr bump --all --alpha           # enter alpha: X.Y.Za1.dev0
uvr bump --all --beta            # enter beta:  X.Y.Zb1.dev0
uvr bump --all --rc              # release candidate: X.Y.Zrc1.dev0
uvr bump --all --stable          # strip pre-release: X.Y.Z.dev0
```

## How versioning works

The version in `pyproject.toml` always ends with `.devN` between releases. When you run `uvr release`, it strips `.devN` and publishes whatever is underneath. After CI finishes, it bumps the patch version and adds `.dev0` back.

```
0.2.0.dev0  →  uvr release  →  publishes 0.2.0  →  CI bumps to 0.2.1.dev0
```

So `uvr bump` controls *what* gets released, and `uvr release` controls *when*.

---

**Under the hood:** [Change detection internals](../under-the-hood/02-change-detection.md)
