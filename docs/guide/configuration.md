# Configuration

All `uvr` configuration lives in your root `pyproject.toml` under `[tool.uvr.*]` tables.

## Workspace config

Running `uvr configure` with no flags shows the current configuration.

```bash
uvr configure                                    # show current config
uvr configure --include pkg-alpha pkg-beta       # include specific packages
uvr configure --exclude pkg-gamma                # exclude specific packages
uvr configure --latest pkg-alpha                 # set the latest package
uvr configure --remove pkg-alpha                 # remove a package from lists
uvr configure --clear                            # reset everything
```

By default, all workspace members are included. The `exclude` list is applied after `include`, so you can include a broad set and then exclude specific packages from it.

```toml
[tool.uvr.config]
latest = "pkg-alpha"
python_version = "3.12"
include = ["pkg-alpha", "pkg-beta"]
exclude = ["pkg-gamma"]
```

## Build runners

By default, every package builds on `ubuntu-latest`. To build on multiple platforms, assign runners per package.

Running `uvr configure runners` with no flags shows all configured runners.

```bash
uvr configure runners                                              # show all runners
uvr configure runners --package pkg-alpha --add macos-latest       # add a runner
uvr configure runners --package pkg-alpha --remove macos-latest    # remove a runner
uvr configure runners --package pkg-alpha --clear                  # reset to default
```

```toml
[tool.uvr.runners]
pkg-alpha = [["ubuntu-latest"], ["macos-latest"]]
```

Each inner list is a set of runner labels for a single matrix entry. Use multiple labels for composite runners (e.g., `["self-hosted", "linux", "arm64"]`). Packages not listed in the runners table default to `ubuntu-latest`.

## Publishing

Publishing requires a named index in your `pyproject.toml` with a `publish-url`.

```toml
[[tool.uv.index]]
name = "pypi"
url = "https://pypi.org/simple/"
publish-url = "https://upload.pypi.org/legacy/"
```

Then configure `uvr` to use it.

```bash
uvr configure publish --index pypi --environment pypi-publish
uvr configure publish --trusted-publishing automatic
uvr configure publish --exclude pkg-debug
uvr configure publish --include pkg-alpha
uvr configure publish --remove pkg-debug
uvr configure publish --clear
```

```toml
[tool.uvr.publish]
index = "pypi"
environment = "pypi-publish"
trusted-publishing = "automatic"
exclude = ["pkg-debug"]
```

The `environment` field enables [trusted publishing](https://docs.pypi.org/trusted-publishers/) (OIDC). No API tokens needed. The `index` value must match the `name` of one of your `[[tool.uv.index]]` entries.

## Configuration reference

This is the complete set of `[tool.uvr.*]` tables with all available keys.

```toml
[tool.uvr.config]
include = ["pkg-alpha"]
exclude = ["pkg-internal"]
latest = "pkg-alpha"
python_version = "3.12"

[tool.uvr.runners]
pkg-alpha = [["ubuntu-latest"], ["macos-latest"]]

[[tool.uv.index]]
name = "pypi"
url = "https://pypi.org/simple/"
publish-url = "https://upload.pypi.org/legacy/"

[tool.uvr.publish]
index = "pypi"
environment = "pypi-publish"
trusted-publishing = "automatic"
include = ["pkg-alpha"]
exclude = ["pkg-debug"]

[tool.uvr.hooks]
file = "uvr_hooks.py"
```

## Custom workflow jobs

The generated `release.yml` has five core jobs. Add your own by editing the YAML directly and wiring them into the pipeline via `needs`.

### Tests before build

```yaml
checks:
  runs-on: ubuntu-latest
  if: ${{ !contains(fromJSON(inputs.plan).skip, 'checks') }}
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v6
    - run: uv sync --all-packages
    - run: uv run poe check
    - run: uv run poe test

build:
  needs: [checks]
  # ... (rest unchanged)
```

### Slack notifications

```yaml
notify:
  runs-on: ubuntu-latest
  needs: [bump]
  if: ${{ always() && !failure() && !cancelled() }}
  steps:
    - name: Notify Slack
      env:
        UVR_PLAN: ${{ inputs.plan }}
      run: |
        CHANGED=$(echo "$UVR_PLAN" | jq -r '.changed | keys | join(", ")')
        curl -X POST "$SLACK_WEBHOOK" -d "{\"text\": \"Released: $CHANGED\"}"
```

### Accessing the plan

The full release plan JSON is available as <code v-pre>${{ inputs.plan }}</code>. Use `fromJSON(inputs.plan)` in expressions to extract fields.

```yaml
if: fromJSON(inputs.plan).changed['my-package'] != null
env:
  VERSION: ${{ fromJSON(inputs.plan).changed['my-package'].release_version }}
```

### Tips

- Add <code v-pre>if: ${{ !contains(fromJSON(inputs.plan).skip, '&lt;job-name&gt;') }}</code> so your job can be skipped with `--skip`.
- Use `always() && !failure() && !cancelled()` for jobs that follow skippable upstream jobs.
- Run `uvr workflow validate` after editing to confirm the YAML is still valid.

## Python hooks

Create `uvr_hooks.py` at your workspace root and `uvr` discovers it automatically.

```python
from uv_release import Hooks


class MyHooks(Hooks):
    def post_plan(self, root, command, plan):
        # Inspect or transform the plan before dispatch
        return plan
```

For a custom path, configure it explicitly in your `pyproject.toml`.

```toml
[tool.uvr.hooks]
file = "scripts/my_hooks.py:MyHook"
```

### Local hooks

These run on your machine during `uvr release`.

| Method | Signature | Returns |
|---|---|---|
| `pre_plan` | `(self, root, command)` | `None` |
| `post_plan` | `(self, root, command, plan)` | Modified plan or `None` |

### CI hooks

These run during executor phases in GitHub Actions or locally with `--where local`.

| Method | When |
|---|---|
| `pre_build` / `post_build` | Before and after the build phase |
| `pre_release` / `post_release` | Before and after GitHub release creation |
| `pre_publish` / `post_publish` | Before and after index publishing |
| `pre_bump` / `post_bump` | Before and after the version bump phase |
| `pre_command` / `post_command` | Before and after every individual command |

The `pre_command` and `post_command` hooks receive the job name and command object. The `post_command` hook also receives the return code.

The plan is a frozen model. The `post_plan` hook cannot mutate it in place. Return a new plan to replace it, or return `None` to keep the original.

## Workflow management

The `uvr workflow` subcommands manage the generated `release.yml` file.

### Validating the workflow

`uvr workflow validate` checks the YAML structure and verifies that all five required jobs exist (`validate`, `build`, `release`, `publish`, `bump`). It never modifies the file.

```bash
uvr workflow validate                # check structure and frozen fields
uvr workflow validate --diff         # also show the diff against the template
```

### Scaffolding and upgrading

`uvr workflow install` generates the workflow file from the bundled template.

```bash
uvr workflow install                              # scaffold the workflow
uvr workflow install --upgrade                    # three-way merge with your customizations
uvr workflow install --upgrade --editor code      # resolve conflicts in VS Code
uvr workflow install --force                      # overwrite with the bundled template
```

The three-way merge compares three sources:

1. **Base** — the bundled template from the `uvr` version recorded in `[tool.uvr.config].workflow-version` (the version you last accepted). Fetched on demand via `uvx --from uv-release=={version}`.
2. **Current** — your current customized file on disk.
3. **Incoming** — the bundled template from the `uvr` version you have installed now.

Your custom jobs survive upgrades because the merge preserves user additions. `workflow-version` is updated only after a successful merge.
