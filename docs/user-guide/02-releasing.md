# Release Your Packages

## Basic release

```bash
uvr release
```

This scans your workspace, detects what changed since the last release, shows a summary, and asks for confirmation before dispatching to GitHub Actions.

The summary shows:
- **Packages** — which changed and which are reused from prior releases
- **Dependency pins** — if any internal dependency constraints need updating
- **Pipeline** — which jobs will run, with build layers grouped by runner

## Skip the prompt

```bash
uvr release -y
```

## Rebuild everything

```bash
uvr release --rebuild-all
```

Ignores change detection and rebuilds every package.

## Pin a Python version

```bash
uvr release --python 3.11
```

Defaults to `3.12`.

## Dependency pin updates

If packages depend on each other and their pins are stale, uvr shows them and prompts:

```
Dependency pins
---------------
  pkg-beta
    pkg-alpha>=0.1.5 -> pkg-alpha>=0.1.10

Write dependency pin updates? [y/N]
```

Accept to write the updated pins, then commit and re-run:

```bash
git add -A && git commit -m "chore: update dependency pins" && git push
uvr release
```

## Version bumping

You control **major.minor** by editing `version` in each package's `pyproject.toml`. CI controls **patch** — after every release, it bumps the patch number and appends `.dev0`.

To bump minor before releasing:

```bash
uv version --bump minor --directory packages/my-pkg
```

## Print raw plan JSON

```bash
uvr release --json
```

Useful for debugging or piping to other tools.
---

**Under the hood:** [Change detection internals](../under-the-hood/02-change-detection.md)
