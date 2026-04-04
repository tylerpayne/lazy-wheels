# Check Status

Preview workspace package status before releasing.

```bash
uvr status
```

This shows every package, its current version, change status, and warnings (like version conflicts).

```
Packages
--------
  STATUS     PACKAGE      VERSION    PREVIOUS  DIFF FROM              CHANGES  COMMITS
  changed    pkg-alpha    0.1.11     0.1.10    pkg-alpha/v0.1.10-dev  3        2
  changed    pkg-beta     0.1.15     0.1.14    pkg-beta/v0.1.14-dev   1        1
  unchanged  pkg-gamma    1.0.0      1.0.0     pkg-gamma/v1.0.0-dev   -        -
```

## Show all as changed

```bash
uvr status --rebuild-all
```

Useful to preview what a full rebuild would look like.
