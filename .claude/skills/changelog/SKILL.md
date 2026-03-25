---
name: changelog
description: Update a CHANGELOG.md following Keep a Changelog format. Use when user says "update changelog", "add changelog entry", "document changes", or when recording notable changes for a release. Also invoked by the /release skill.
argument-hint: "[description of changes or version number]"
---

# Updating the Changelog

There is a single changelog at `docs/CHANGELOG.md` covering all project changes. It follows [Keep a Changelog 1.1.0](https://keepachangelog.com/).

## Core Rules

- The changelog is for **humans, not machines**. Write entries that help users understand what changed and why.
- Do NOT paste commit messages. Commits document source code evolution; changelog entries communicate noteworthy differences to end users.
- Every entry must be categorized under exactly one of these sections (in this order):
  - **Added** — new features
  - **Changed** — modifications to existing functionality
  - **Deprecated** — features slated for removal
  - **Removed** — features no longer present
  - **Fixed** — bug corrections
  - **Security** — vulnerability patches
- Only include sections that have entries. Do not add empty sections.
- Omit changes that don't affect users (internal refactors, test-only changes, CI tweaks, dev tooling updates) unless they are significant enough to be notable.

## Process

### Adding entries during development (no version number)

1. Read `docs/CHANGELOG.md`
2. Add entries under `## [Unreleased]`, creating the appropriate section heading if it doesn't exist
3. Each entry is a bullet point starting with `- `
4. Write in imperative mood, starting with a verb: "Add", "Fix", "Remove", "Change", "Deprecate"
5. Be specific: name the function, class, or behavior that changed

### Cutting a release (version number provided)

1. Read `docs/CHANGELOG.md`
2. Determine today's date in ISO 8601 format (YYYY-MM-DD)
3. Rename `## [Unreleased]` section content into a new version section:
   ```markdown
   ## [Unreleased]

   ## [v0.5.1] - 2026-03-25

   ### Added
   - ...
   ```
4. Review `git log` since the last release tag — add entries for any changes not already captured under `[Unreleased]`
5. Leave an empty `## [Unreleased]` heading at the top
6. Versions are listed newest-first

### Writing good entries

Before writing, consult `references/style-guide.md` for:
- Entry formatting rules and examples
- How to handle breaking changes, deprecations, and yanked releases
- Anti-patterns to avoid (commit log dumps, vague descriptions, inconsistent coverage)

## Example

User says: "Update the changelog — we added hook upserts and fixed a pin update bug"

Result in `docs/CHANGELOG.md`:
```markdown
## [Unreleased]

### Added
- Add `--id` flag to `uvr hooks add` for idempotent step upserts

### Fixed
- Fix dependency pin updates not detecting already-pinned constraints
```

## Troubleshooting

### Entries appear under the wrong version
The `[Unreleased]` section must always exist at the top. When cutting a release, entries move from `[Unreleased]` into the new version section — they should never be added directly under a released version.

### Duplicate entries
Before adding an entry, scan the existing `[Unreleased]` section. If a change was already recorded (perhaps by a previous conversation), update the existing entry rather than adding a duplicate.
