# `uvr wheels`

Download platform-compatible wheels from GitHub releases or CI run artifacts without installing them.

```bash
uvr wheels ORG/REPO/PKG              # latest release
uvr wheels ORG/REPO/PKG@1.2.3       # specific version
uvr wheels ORG/REPO/PKG --run-id ID  # from CI artifacts
```

## Flags

| Flag | Description |
|------|-------------|
| `-o`, `--output` | Directory to save wheels into (default: `dist/`) |
| `--release-tag` | Download from a specific GitHub release tag |
| `--run-id` | Download from a GitHub Actions run's artifacts |

## Resolution order

1. `--run-id` — download from a workflow run's uploaded artifacts
2. `--release-tag` — download from an explicit GitHub release tag
3. `@VERSION` in the spec — resolves to tag `PKG/vVERSION`
4. None of the above — finds the latest release tag for the package

Wheels are filtered by platform compatibility before saving.
