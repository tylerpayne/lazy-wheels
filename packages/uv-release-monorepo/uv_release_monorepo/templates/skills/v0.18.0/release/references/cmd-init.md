# `uvr init`

Scaffold the GitHub Actions release workflow into your repo.

```bash
uvr init
```

Creates `.github/workflows/release.yml` with three core jobs: **build**, **publish**, and **finalize**. Run this once when setting up a new repo.

The generated workflow contains only the core pipeline. You can add custom jobs (tests, linting, PyPI publish, etc.) by editing the YAML directly — see `pipeline.md`.

## Flags

| Flag | Description |
|------|-------------|
| `--force` | Overwrite an existing `release.yml` (loses any custom jobs you added) |
| `--workflow-dir DIR` | Write to a different directory (default: `.github/workflows`) |

## Notes

- Requires a git repo with a `pyproject.toml` that defines `[tool.uv.workspace]` members.
- After scaffolding, edit the workflow to add custom jobs for your project's quality gates.
- Run `uvr validate` after manual edits to catch schema errors (see `cmd-validate.md`).
- `--force` overwrites the entire file. If you have custom jobs, back up first or re-add them after.
