# Support Single-Package Workspaces

* Status: accepted
* Date: 2026-05-14

## Context and Problem Statement

uv-release historically assumed the repository was a uv multi-package workspace. `provide_workspace_packages` parsed the root `pyproject.toml` only for its `[tool.uv.workspace].members` glob and discovered every package as a subdirectory. The `Package` entity's `path` field always pointed at a workspace-member directory like `packages/pkg-a`, never the workspace root.

uv itself supports a simpler shape that uv-release did not. A `pyproject.toml` that carries `[project]` plus `[build-system]` and no `[tool.uv.workspace]` block is a fully valid uv project. For small repositories with one publishable package this shape avoids the `packages/<pkg>/pyproject.toml` indirection and the `[tool.uv.workspace]` block entirely. Users releasing a single library currently have to either adopt the multi-package layout artificially or skip uv-release.

How should uv-release discover packages when the root `pyproject.toml` is itself the package?

## Decision Drivers

* uv natively supports plain single-package projects. uv-release should not require a workspace block when uv does not.
* Multi-package and single-package layouts are visibly different shapes of `pyproject.toml`. The provider can branch on what's there rather than guess.
* The intermediate shape ("workspace root that is itself a member", e.g. `members = ["."]` with `[project]` on the root) is rare and ambiguous. Two valid interpretations during discovery (root-as-itself vs root-via-glob) would produce duplicates or inconsistent state.
* Most code downstream of discovery is already keyed off the `Package` entity, not the path. Tag format, build order, plan rendering, and CI dispatch are path-shape-agnostic. Only the small handful of sites that derived display names from `Path(package_path).name` need adjusting.
* `[tool.uvr.config].latest` selects the GitHub release marked "Latest" across packages. With one package there is nothing to select between; requiring the user to write `latest = "<name>"` is busywork in the single-package case.

## Considered Options

* Keep multi-package as the only supported shape; document a `members = ["."]` workaround for single-package repos.
* Support single-package as a third shape alongside the workspace-root-as-member shape and the standard multi-package layout.
* Support single-package only (root has `[project]` and no `[tool.uv.workspace]`); reject the workspace-root-as-member shape with an error for now.

## Decision Outcome

Chosen option: support single-package only, reject root-as-member.

`RootPyProject` gains optional `project` and `build_system` fields. `provide_workspace_packages` branches on which top-level tables are present in the root:

* `[project]` and no `[tool.uv.workspace]` → emit one `Package` with `path = "."` from the root pyproject.
* `[tool.uv.workspace]` and no `[project]` → existing glob behavior, unchanged.
* Both present → raise `ValueError`. The root is ambiguous as both a discrete package and a workspace root, and uv-release does not yet handle deduplication for that shape.
* Neither present → existing fallthrough (empty workspace). Several commands tolerate this and the previous behavior is preserved.

`SetVersionCommand` and `BuildCommand` carry the package name explicitly (`package_name` field). Previously they derived a display name from `Path(package_path).name` or `Path(package_path).parent.name`, both of which are empty strings when `package_path` is `"."`. Threading the name through is a tiny change and removes the layout assumption from the command layer entirely.

`UvrConfig` falls back to the sole package name when `[tool.uvr.config].latest` is empty and the workspace has exactly one package. The "latest" marker is only meaningful when there is something to choose between, so the single-package case auto-defaults.

### Positive Consequences

* Plain `pip install`-style repositories adopt uv-release without restructuring into `packages/<name>/`.
* `Path(".")` is a valid git pathspec and a valid `uv build` cwd, so change detection, build, and tag construction work unmodified.
* The shape check is a single branch with a single rejected combination, keeping the discovery logic readable.
* `Package.name` becomes the canonical display name everywhere; the path-as-name shortcut is gone.
* Removing the implicit "latest defaults to empty string" in one-package workspaces makes the common case match user intent without configuration.

### Negative Consequences

* `pyproject.toml` files that combine `[project]` and `[tool.uv.workspace]` (legal under uv) raise on `uvr` invocation. This is intentional but a behavior change for any existing setup that relied on the ambiguous shape working silently as a workspace.
* The single-package layout cannot grow into a multi-package workspace by adding `[tool.uv.workspace]` without first migrating `[project]` into a subdirectory. The migration is mechanical but is now load-bearing in uv-release, not just a uv-side convention.
* `UvrConfig.latest_package` default depends on `WorkspacePackages`, introducing a new dependency edge between `dependencies/config` and `dependencies/shared`. The direction is one-way (config consumes packages) and matches the existing import-direction rule, but it widens the config provider's surface.

## Pros and Cons of the Options

### Keep multi-package as the only shape

* Good, because the discovery path stays simple — one shape, one glob.
* Good, because no new ambiguity around what "the root package" means.
* Bad, because users with a single-library repo have to scaffold a phantom `packages/<name>/` layer.
* Bad, because the gap between "what uv supports" and "what uv-release supports" widens as uv evolves the plain-project shape.

### Support single-package and root-as-member together

* Good, because every legal uv shape is supported.
* Bad, because the root-as-member shape (root has both `[project]` and `[tool.uv.workspace]` with `members = ["."]`) requires deduplication during discovery (the root would otherwise appear twice). The dedup rule is non-obvious and easy to get wrong silently.
* Bad, because explicit rejection produces a clear actionable error today, while supporting the shape with dedup logic costs design effort for a use case nobody is asking for.

### Support single-package only, reject root-as-member (chosen)

* Good, because the two supported shapes are visibly disjoint at the file level (presence/absence of `[project]` and `[tool.uv.workspace]`), with no inference needed.
* Good, because the rejected shape is rejected loudly with a message that names both offending tables.
* Good, because adding root-as-member later is purely additive: replace the raise with a code path, keeping single-package behavior unchanged.
* Bad, because the root-as-member shape is illegal under uv-release even though uv itself accepts it. Anyone arriving with that layout has to migrate.

## Links

* Refines [ADR-0014](0014-restructure-shared-module-architecture.md)
