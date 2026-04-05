# Configuration

All <code class="brand-code">uvr</code> configuration lives in your root `pyproject.toml` under `[tool.uvr.*]` tables.

## Filter packages

By default, all workspace members are included. Use include or exclude to control which packages participate in releases.

```bash
uvr workflow config --include pkg-alpha pkg-beta
uvr workflow config --exclude pkg-gamma
uvr workflow config --latest pkg-alpha
uvr workflow config                          # show current config
```

Stored in `pyproject.toml`.

```toml
[tool.uvr.config]
include = ["pkg-alpha", "pkg-beta"]
exclude = ["pkg-gamma"]
latest = "pkg-alpha"
```

`exclude` is applied after `include`. Use `--remove` to remove packages from lists, or `--clear` to reset everything.

## Build runners

By default, every package builds on `ubuntu-latest`. To build on multiple platforms, assign runners per package.

```bash
uvr workflow runners pkg-alpha --add macos-latest windows-latest
uvr workflow runners pkg-alpha --remove windows-latest
uvr workflow runners pkg-alpha --clear
uvr workflow runners                     # show all
```

Stored in `pyproject.toml`.

```toml
[tool.uvr.runners]
pkg-alpha = [["ubuntu-latest"], ["macos-latest"]]
```

Each inner list is a set of runner labels for a single matrix entry. Use multiple labels for composite runners (e.g., `["self-hosted", "linux", "arm64"]`).

## Publishing

<code class="brand-code">uvr</code> can publish wheels to package indexes after creating GitHub releases. Publishing requires a named index in your `pyproject.toml` with a `publish-url`.

```toml
[[tool.uv.index]]
name = "pypi"
url = "https://pypi.org/simple/"
publish-url = "https://upload.pypi.org/legacy/"
```

Then configure <code class="brand-code">uvr</code> to use it.

```bash
uvr workflow publish --index pypi --environment pypi-publish
uvr workflow publish --trusted-publishing always
uvr workflow publish --exclude pkg-debug
```

Stored in `pyproject.toml`.

```toml
[tool.uvr.publish]
index = "pypi"                        # must match a [[tool.uv.index]] name
environment = "pypi-publish"          # GitHub Actions environment
trusted-publishing = "automatic"      # "automatic", "always", or "never"
exclude = ["pkg-debug"]
```

The `environment` field enables [trusted publishing](https://docs.pypi.org/trusted-publishers/) (OIDC). No API tokens needed.

## Python hooks

Place `uvr_hooks.py` at your workspace root with a `ReleaseHook` subclass and <code class="brand-code">uvr</code> discovers it automatically. For a custom path, configure it explicitly.

```toml
[tool.uvr.hooks]
file = "scripts/my_hooks.py:MyHook"
```

See [Customizing the Pipeline](06-customization.md) for the full hook API and examples.

## Preferred editor

```bash
uvr workflow config --editor code
```

Used for conflict resolution during `uvr workflow init --upgrade`.

---

**Under the hood.** [Build](../under-the-hood/03-build.md) | [Workflow](../under-the-hood/04-workflow.md)
