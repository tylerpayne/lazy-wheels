# Under the Hood

How <code class="brand-code">uvr</code> works internally. The design decisions, algorithms, and data structures behind the CLI.

## Start here

- [Architecture](architecture.md):The plan+execute model and how the pieces fit together.

## Deep dives

- [Change Detection](01-change-detection.md):Tag formats, diffing, and transitive propagation.
- [Bump](02-bump.md):Automatic dependency pinning and version management.
- [Build](03-build.md):Topologically layered builds with per-runner matrices.
- [Workflow](04-workflow.md):A stable CI template you never debug.
- [Release](05-release.md):From change detection to published wheels.
- [Package States](package-states.md):The complete state machine, data model, and failure modes.
