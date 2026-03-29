# Set Up Your First Release

## Prerequisites

- [uv](https://github.com/astral-sh/uv) installed
- A git repository hosted on GitHub with Actions enabled
- A workspace root `pyproject.toml` with `[tool.uv.workspace]` members defined
- The [GitHub CLI](https://cli.github.com/) (`gh`) authenticated

## Install uvr

```bash
uv tool install uv-release-monorepo
```

## Generate the workflow

```bash
uvr init
```

This creates `.github/workflows/release.yml` with all seven pipeline jobs. Four are hook slots (pre-build, post-build, pre-release, post-release) that default to a no-op and are auto-skipped. Four are the core pipeline (uvr-validate, uvr-build, uvr-release, uvr-finalize).

## Customize the workflow

Edit `release.yml` directly to add your hook steps — tests, linting, PyPI publish, notifications. See:

- [Add CI hooks](04-hooks.md) for tests and linting
- [Publish to PyPI](05-pypi.md) for trusted publishing

After editing, validate:

```bash
uvr validate
```

## Commit and release

```bash
git add .github/workflows/release.yml
git commit -m "Add release workflow"
git push
uvr release
```

## Check your configuration

```bash
uvr status
```
---

**Under the hood:** [Init and validation internals](../under-the-hood/01-init-and-validation.md)
