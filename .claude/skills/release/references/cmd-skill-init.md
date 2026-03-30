# `uvr skill init`

Copy bundled Claude Code skills into your project.

```bash
uvr skill init                   # write skills to .claude/skills/
uvr skill init --force           # overwrite existing skill files
uvr skill init --upgrade         # three-way merge latest skills into existing files
uvr skill init --base-only       # write merge bases without touching actual files
```

Copies the release skill and its references into `.claude/skills/` in the current directory. Existing files are skipped unless `--force` is used.

## Flags

`--force`, `--upgrade`, and `--base-only` are mutually exclusive.

| Flag | Description |
|------|-------------|
| `--force` | Overwrite existing skill files |
| `--upgrade` | Three-way merge the latest bundled skills into existing files, preserving your customizations |
| `--base-only` | Write merge bases to `.uvr/bases/` without touching actual files |
| `--editor EDITOR` | Editor to use for conflict resolution during upgrade (e.g. `code`, `vim`) |

## Upgrading

When a new version of `uvr` ships skill changes, run:

```bash
uvr skill init --upgrade
```

If merge bases are missing, recover them first:

```bash
uvx --from uv-release-monorepo==<old-version> uvr skill init --base-only
uvr skill init --upgrade
```
