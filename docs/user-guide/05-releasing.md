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

## Print raw plan JSON

```bash
uvr release --json
```

Useful for debugging or piping to other tools.

---

**Under the hood:** [CI execution internals](../under-the-hood/07-ci-execution.md)
