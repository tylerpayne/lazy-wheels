# Changelog Entry Style Guide

Based on [Keep a Changelog 1.1.0](https://keepachangelog.com/).

## Entry Format

Each entry is a markdown bullet point under a section heading.

```markdown
### Added
- Add `ClassName` for doing X
```

### Rules

- Start with an imperative verb: Add, Fix, Remove, Change, Deprecate, Update
- Name the specific thing that changed (class, function, config key, behavior)
- One logical change per bullet point — don't combine unrelated things
- If a change has user-facing impact, explain what the user sees differently
- Keep entries to one or two sentences

### Good entries

```markdown
- Add `--id` flag to `uvr hooks add` for idempotent step upserts
- Fix dependency pin updates not detecting already-pinned constraints
- Remove deprecated `--tag-prefix` CLI flag (use default `{pkg}/v{version}` format)
- Change default Python version from 3.11 to 3.12 in CI builds
- Deprecate `old_helper()` in favor of `new_helper()` — will be removed in v1.0
```

### Bad entries

```markdown
# Too vague — what was fixed?
- Fix bug

# Commit message dump — not user-facing
- Merge branch 'feature/hooks' into main

# Internal detail — users don't care
- Refactor internal helper functions in utils.py

# Multiple unrelated changes in one bullet
- Add hook upserts, fix pin bug, and update docs
```

## Section Ordering

Always use this order (omit sections with no entries):

1. **Added** — new features
2. **Changed** — modifications to existing functionality
3. **Deprecated** — soon-to-be removed features (include migration path)
4. **Removed** — now removed features
5. **Fixed** — bug fixes
6. **Security** — vulnerability fixes (include CVE if available)

## Version Headings

Format: `## [vX.Y.Z] - YYYY-MM-DD`

- Use ISO 8601 dates (YYYY-MM-DD), never regional formats
- Newest version appears first
- The `[Unreleased]` section is always at the top

## Breaking Changes

When a change breaks backward compatibility:
- Place it under the appropriate section (usually **Changed** or **Removed**)
- Prefix the entry with `**BREAKING**: ` to make it visually obvious
- Include a migration path or alternative

```markdown
### Changed
- **BREAKING**: Rename `--matrix` short flag from `-m` to require full `--matrix` — update all scripts
```

## Deprecations

When deprecating, always include:
- What is deprecated
- What replaces it
- When it will be removed (if known)

```markdown
### Deprecated
- Deprecate `uvr run --local` — use `uvr release` instead. Will be removed in v1.0.
```

## Yanked Releases

If a released version is pulled due to a serious bug or security issue:

```markdown
## [v0.5.0] - 2026-03-20 [YANKED]
```

The `[YANKED]` tag must appear on the version heading line.

## What NOT to Include

- Commit messages or merge commit descriptions
- Internal refactors that don't change behavior
- Test-only changes
- CI/CD pipeline changes (unless they affect how users install or use the package)
- Documentation-only changes (unless significant, like a new getting-started guide)
- Version bumps of internal dev dependencies
