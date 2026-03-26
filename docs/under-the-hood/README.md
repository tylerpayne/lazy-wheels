# Internals

Under-the-hood documentation for uvr developers. Each file maps to one or more
[user guide](../user-guide/README.md) topics and explains the code paths, data models,
and design decisions behind them.

## Contents

1. [Init and validation](01-init-and-validation.md) -- `uvr init`, `uvr validate`, the `ReleaseWorkflow` model, and `_frozen` field protection.
2. [Change detection](02-change-detection.md) -- `build_plan()` discovery, dev baseline tags, git diffing, and dependency-graph propagation.
3. [Dependency pinning](03-dependency-pinning.md) -- how internal dep pins are computed, `update_dep_pins()`, and the write-prompt flow.
4. [Build matrix](04-build-matrix.md) -- matrix expansion, `topo_layers()`, per-runner grouping, and `uvr-steps build-all`.
5. [Workflow model](05-workflow-model.md) -- `ReleaseWorkflow`, all job types, `_frozen`, `_needs_validator`, `_NOOP_STEPS`, serialization.
6. [Release plan](06-release-plan.md) -- `ReleasePlan` fields, `skip`/`reuse_run_id`/`uvr_install`, schema versioning.
7. [CI execution](07-ci-execution.md) -- `uvr-steps` dispatch, what each CI step does, the `fromJSON(inputs.plan)` pattern.
