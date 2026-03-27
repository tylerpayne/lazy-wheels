# Release Pipeline

`uvr init` scaffolds a `release.yml` with three core jobs:

```
build → publish → finalize
```

- **build** — builds wheels for changed packages (matrix over runners), uploads them as artifacts
- **publish** — downloads artifacts, creates one GitHub release per changed package with wheels attached
- **finalize** — tags, bumps to next dev version, pins internal deps, commits, and pushes

Each core job's `if`, `strategy`, `runs-on`, and `steps` are frozen by uvr. `uvr validate` will warn if you modify them. The `needs` list can be extended.

See also:
- `release-plan.md` — what the release plan JSON contains
- `custom-jobs.md` — how to add your own jobs to the workflow
- `cmd-runners.md` — configure per-package build runners (cross-platform wheels)
- `cmd-install.md` — install packages from the GitHub releases that publish creates
