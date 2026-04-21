# `uvr status`

Show which packages have changed since their last release baseline.

```bash
uvr status
```

Displays each package's name, version, and change reason (files changed, initial release, dependency changed, or unchanged).

## Flags

| Flag | Description |
|------|-------------|
| `--all-packages` | Show all packages as changed |
| `--packages PKG...` | Show specific packages |
