# `uvr runners`

Manage per-package build runners. By default, all packages build on `ubuntu-latest`. Use this to add platform-specific runners for cross-platform wheel builds.

```bash
uvr runners                      # show all package runner configs
uvr runners my-pkg               # show runners for a specific package
```

## Mutation flags

Mutually exclusive, require a package name:

| Flag | Description |
|------|-------------|
| `--add RUNNER` | Add a runner to the package (e.g., `--add macos-latest`) |
| `--remove RUNNER` | Remove a runner from the package |
| `--clear` | Remove all custom runners (revert to default) |

```bash
uvr runners my-pkg --add macos-latest
uvr runners my-pkg --remove windows-latest
uvr runners my-pkg --clear
```

Runner configuration is stored in `[tool.uvr.matrix]` in the root `pyproject.toml`. The build job's matrix expands to one job per unique runner, and each runner builds all packages assigned to it.
