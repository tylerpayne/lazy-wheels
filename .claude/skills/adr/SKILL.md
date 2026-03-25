---
name: adr
description: Write an Architecture Decision Record (ADR) in MADR format using the collaborative pyadr workflow. Use when user says "document this decision", "write an ADR", "why did we choose", "record this architecture choice", or needs to capture a decision that is hard or costly to reverse.
argument-hint: "[short title of the decision]"
---

# Writing Architecture Decision Records

ADRs use the [MADR](https://adr.github.io/madr/) format and live in `docs/adr/` at the workspace root. All decisions — whether about the CLI, the release pipeline, CI, or tooling — are recorded here. There is only one releasable package (`uv-release-monorepo`) so a single ADR directory is sufficient.

See also: [ADR practices](https://adr.github.io/ad-practices/).

## Process

Writing an ADR is always collaborative. Never write one in isolation — the user's input shapes every section.

1. **Agree on the decision to document.** Before scaffolding anything, confirm with the user: what was decided, why it matters, and what alternatives were considered. If the user hasn't thought through alternatives, work through them together.

2. **Scaffold the file:**
   ```bash
   uv run pyadr new <Title Words Here>
   ```
   This creates `docs/adr/XXXX-title-words-here.md` with status `proposed`.

3. **Draft the content together.** Write each section and share it with the user for feedback before moving on. Key checkpoints:
   - **Context**: ask the user what prompted this decision — what changed or broke?
   - **Decision drivers**: ask what constraints mattered most. Don't guess.
   - **Options**: ask the user what alternatives they considered or rejected. Research additional options if needed, but always confirm them with the user.
   - **Outcome and consequences**: ask the user what trade-offs they see. Present your draft of the comparison table for review.

4. **Get explicit approval** of the final content before accepting.

5. **Accept the ADR:**
   ```bash
   uv run pyadr accept docs/adr/XXXX-title-words-here.md
   ```
   This renames the file to `NNNN-title-words-here.md` and sets status to `accepted`.

6. To reject instead: `uv run pyadr reject docs/adr/XXXX-title-words-here.md`

7. To regenerate the table of contents: `uv run pyadr toc`

## When to Create an ADR

Not every decision needs an ADR. Create one when the decision is **architecturally significant** — meaning it is hard or costly to reverse. Ask:

- Would changing this later require significant rework?
- Does this constrain future choices (e.g., build system, dependency, API shape, CI pipeline)?
- Would a new team member be confused about _why_ this choice was made?

If the answer to any of these is yes, write an ADR. If the decision is easily reversible or obvious, skip it. A decision log with 100 entries that nobody reads is worse than 10 well-written ones.

### Good ADR candidates

- Release pipeline architecture (plan+execute, tag strategy, CI workflow design)
- CLI design choices (command structure, flag semantics, interactive vs non-interactive)
- Data model decisions (ReleasePlan schema, BumpPlan, version format)
- Build system and tooling choices (hatchling, Jinja2 templates, dependency resolution strategy)
- `[tool.uvr.config]` design decisions
- Cross-package dependency patterns

### Decisions that don't need an ADR

- Bumping a dependency version (unless it's a major version with breaking changes)
- Adding a test or fixing a bug
- Formatting or lint rule tweaks
- Routine refactoring

## Writing Good ADR Content

Before drafting each section, consult `references/writing-guide.md` for:
- Section-by-section guidance (title, context, drivers, options, outcome)
- Anti-patterns to avoid (Dummy Alternative, Sprint, Fairy Tale, Free Lunch, Pseudo-accuracy)
- Comparison table format (use tables, not pro/con lists)
- Style rules (be concrete, brief, assertive, one decision per ADR)

## Example

User says: "Let's document why we chose hatchling as the build backend"

1. Confirm: "You want to record the choice of hatchling over alternatives like setuptools, flit, or maturin — is that right?"
2. Scaffold: `uv run pyadr new Use Hatchling As Build Backend`
3. Draft context together: "We needed a PEP 517 build backend for the monorepo. What prompted this — were there issues with setuptools?"
4. Draft drivers: ask what mattered (speed, PEP compliance, monorepo support, etc.)
5. Draft options with comparison table, get feedback
6. Write outcome and consequences, get approval
7. Accept: `uv run pyadr accept docs/adr/XXXX-use-hatchling-as-build-backend.md`

Result: `docs/adr/0002-use-hatchling-as-build-backend.md` with status `accepted`.

## Troubleshooting

### `pyadr` command not found
Run `uv sync` to install all workspace dependencies including pyadr.

### `pyadr accept` fails on an already-accepted ADR
The file has already been numbered. Check `docs/adr/` for the numbered version. If the status field is wrong, edit it manually.

### ADR scope is too broad
If you find yourself writing multiple "Decision Outcome" sections or the context covers more than one question, split into separate ADRs. One decision per ADR.
