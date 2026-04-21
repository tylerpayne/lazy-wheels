# Release Pipeline

`uvr workflow init` scaffolds a `release.yml` with five core jobs:

```
validate → build → release → publish → bump
```

- **validate** -- sets release versions for dev packages, commits, and pushes
- **build** -- builds wheels for changed packages (matrix over runners), uploads them as artifacts
- **release** -- downloads build artifacts, tags the release commit, creates one GitHub release per changed package with wheels attached
- **publish** -- downloads build artifacts, publishes wheels to PyPI (or configured index) via trusted publishing
- **bump** -- bumps to next dev version, pins internal deps, creates baseline tags, commits, and pushes

Each core job's `if`, `strategy`, `runs-on`, and `steps` are frozen by uvr. `uvr workflow validate` will warn if you modify them. The `needs` list can be extended.

A concurrency group ensures only one release workflow runs at a time. A second dispatch queues instead of running in parallel.

See also:
- `release-plan.md` -- what the release plan JSON contains
- `custom-jobs.md` -- how to add your own jobs to the workflow
- `cmd-runners.md` -- configure per-package build runners (cross-platform wheels)
- `cmd-install.md` -- install packages from the GitHub releases that release creates
