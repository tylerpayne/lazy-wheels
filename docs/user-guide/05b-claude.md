# Release with Claude

uvr ships with a Claude Code skill that handles the entire release flow interactively. Claude reads your workspace, runs uvr commands, reviews your API, writes release notes, and dispatches to CI.

## Install the skill

```bash
uvr skill init
```

This copies the `/release` skill into your project's `.claude/skills/` directory.

## Use it

Invoke the skill in Claude Code:

```
/release
```

Claude will:

1. **Branch** — create a release branch if you're on main
2. **Preview** — run `uvr release --dry-run` and show what changed
3. **Bump** — ask if any packages need a minor or major bump instead of patch
4. **Review** — audit public API against docstrings and docs, fix discrepancies
5. **Release notes** — draft user-facing notes and present them for your approval
6. **Dispatch** — commit, push, and run `uvr release` to dispatch to CI
7. **Monitor** — watch the workflow and handle failures
8. **Merge** — merge the release branch back to main

## What Claude handles for you

- **Version suggestions** — Claude presents what changed and asks whether patch is appropriate or if you want minor/major
- **API review** — checks that docstrings and docs match the actual exports
- **Release notes** — writes prose (not commit dumps) using [Keep a Changelog](https://keepachangelog.com/) format
- **Failure recovery** — if CI fails, Claude reads the logs and either fixes the issue or uses `--skip-to` / `--reuse-run` to resume

## Upgrading the skill

When uvr updates its skill template:

```bash
uvr skill init --upgrade
```

This three-way merges the latest skill into your existing files, preserving any customizations.
