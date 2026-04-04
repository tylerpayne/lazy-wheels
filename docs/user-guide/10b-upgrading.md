# Upgrading

## Upgrade uvr

```bash
uv add --dev uv-release-monorepo@latest
```

## Upgrade the workflow

When uvr updates its workflow template, upgrade your `release.yml` with a three-way merge that preserves your custom jobs:

```bash
uvr workflow init --upgrade
```

If there are conflicts, uvr opens your editor to resolve them. Set your preferred editor:

```bash
uvr workflow init --upgrade --editor code
```

To inspect what would change without touching files:

```bash
uvr workflow init --base-only
```

This writes merge bases to `.uvr/bases/` for manual comparison.

## Upgrade Claude skills

```bash
uvr skill init --upgrade
```

Same three-way merge — updates the bundled skill templates while preserving your customizations.

## Validate after upgrading

```bash
uvr workflow validate
```

Reports errors for invalid structure and warnings for modified core job fields.
