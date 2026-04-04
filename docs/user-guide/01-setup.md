# Set Up Your First Release

## Prerequisites

- [uv](https://github.com/astral-sh/uv) installed
- A git repository hosted on GitHub with Actions enabled
- A workspace root `pyproject.toml` with `[tool.uv.workspace]` members defined
- The [GitHub CLI](https://cli.github.com/) (`gh`) authenticated

## Install uvr

```bash
uv add --dev uv-release-monorepo
```

## Generate the workflow

```bash
uvr workflow init
```

This creates `.github/workflows/release.yml` with four core jobs: `uvr-validate`, `uvr-build`, `uvr-release`, and `uvr-bump`. You can add custom jobs (tests, linting, PyPI publish) by editing the YAML directly — see [Custom workflow jobs](08-custom-jobs.md).

After editing, validate:

```bash
uvr workflow validate
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
uvr release --dry-run
```
---

**Under the hood:** [Init and validation internals](../under-the-hood/01-init-and-validation.md)
