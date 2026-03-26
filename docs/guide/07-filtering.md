# Filter Which Packages Are Released

If your workspace has packages that shouldn't be part of the release cycle (dev tools, test fixtures, etc.), configure include/exclude lists.

## Allowlist (include)

Only release these packages:

```toml
[tool.uvr.config]
include = ["pkg-alpha", "pkg-beta"]
```

## Denylist (exclude)

Release everything except these:

```toml
[tool.uvr.config]
exclude = ["pkg-internal", "pkg-dev-tools"]
```

## Combined

`exclude` is applied after `include`. If `include` is set, only listed packages are considered first, then `exclude` filters from that set.

## Mark a package as "Latest"

The `latest` key controls which package's GitHub Release gets the "Latest" badge:

```toml
[tool.uvr.config]
latest = "my-main-package"
```

## Where to put the config

All uvr config lives in the workspace root `pyproject.toml` under `[tool.uvr.config]`.
