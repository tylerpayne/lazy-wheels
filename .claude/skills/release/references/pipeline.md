# Release Pipeline

`uvr workflow init` scaffolds a `release.yml` with three core jobs:

```
build → release → bump
```

- **build** — builds wheels for changed packages (matrix over runners), uploads them as artifacts
- **release** — tags the release commit, creates one GitHub release per changed package via `gh release create` with wheels attached, pushes release tags
- **bump** — bumps to next dev version, pins internal deps, commits, and pushes

Each core job's `if`, `strategy`, `runs-on`, and `steps` are frozen by uvr. `uvr workflow validate` will warn if you modify them. The `needs` list can be extended.

See also:
- `release-plan.md` — what the release plan JSON contains
- `custom-jobs.md` — how to add your own jobs to the workflow
- `cmd-runners.md` — configure per-package build runners (cross-platform wheels)
- `cmd-install.md` — install packages from the GitHub releases
