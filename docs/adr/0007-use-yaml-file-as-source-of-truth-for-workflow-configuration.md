# Use YAML File as Source of Truth for Workflow Configuration

* Status: accepted
* Date: 2026-03-25

## Context and Problem Statement

`uvr` needs a way for users to customize the generated `release.yml` — adding workflow-level permissions (`id-token: write`), setting job-level properties (`environment: pypi`), and managing arbitrary YAML keys. The initial approach stored these settings in `[tool.uvr.permissions]` and `[tool.uvr.jobs]` in `pyproject.toml`, then rendered them into the YAML via the Jinja2 template. This duplicated state: the same values lived in both `pyproject.toml` and `release.yml`, and the two could drift. Where should workflow configuration live?

## Decision Drivers

- **No duplication**: a setting should exist in exactly one place
- **Generality**: users should be able to set any valid GitHub Actions YAML key, not just the ones we anticipate
- **Consistency with hooks**: hook steps are already stored in and extracted from the YAML file, not `pyproject.toml`

## Considered Options

- Store in `pyproject.toml`, render into YAML via template
- Edit the YAML file directly — load as dict, mutate, validate, serialize back

## Decision Outcome

Chosen option: "Edit the YAML directly", because it eliminates duplication entirely. The YAML file is the single source of truth. `uvr workflow` loads it as a Python dict, applies the edit, validates the result against a `ReleaseWorkflow` Pydantic model, and writes it back. No intermediate config in `pyproject.toml`, no template variables to keep in sync.

The `ReleaseWorkflow` model validates the full workflow structure — rejecting unknown job names, enforcing types on known fields, and allowing extra fields on hook jobs for arbitrary GitHub Actions properties.

### Consequences

- Good, because each setting exists in exactly one place — the YAML file
- Good, because `uvr workflow` is fully general — any valid YAML path can be read, written, or deleted without adding new config keys or template variables
- Good, because the mutation vocabulary (`--set`, `--add`, `--insert --at`, `--remove`, `--clear`) mirrors `uvr hooks`, giving users one mental model
- Bad, because `uvr workflow init --force` regenerates from the template and loses customizations that aren't hooks (permissions, job-level settings). Users must re-apply them or avoid `--force`.
- Bad, because PyYAML round-tripping loses comments and formatting from the template-generated file

## Comparison

| Criterion | pyproject.toml + template | Direct YAML editing |
|---|---|---|
| Duplication | High — same values in TOML and YAML | None — YAML is the only copy |
| Generality | Low — each new key needs a TOML schema + template variable | Full — any YAML path works |
| Consistency with hooks | Inconsistent — hooks live in YAML, config in TOML | Consistent — everything in YAML |
| `uvr workflow init` safety | Safe — TOML survives regeneration | Risky — `--force` loses non-hook customizations |
| Formatting preservation | Good — template controls output | Lossy — PyYAML rewrites formatting |

## Links

- Extends [ADR-0001](0001-use-plan-execute-architecture-for-releases.md) — the YAML file remains a pure executor, but now also holds user configuration
