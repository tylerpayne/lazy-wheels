# Configure Build Runners

By default every package builds on `ubuntu-latest`. If a package needs native compilation on multiple platforms, add runners.

## Add a runner

```bash
uvr workflow runners my-native-pkg --add macos-14
uvr workflow runners my-native-pkg --add windows-latest
```

## Remove a runner

```bash
uvr workflow runners my-native-pkg --remove windows-latest
```

## Clear all runners for a package

```bash
uvr workflow runners my-native-pkg --clear
```

## View current configuration

```bash
uvr workflow runners             # all packages
uvr workflow runners my-pkg      # one package
```

## Where runners are stored

Runner configuration lives in `[tool.uvr.matrix]` in your workspace root `pyproject.toml`:

```toml
[tool.uvr.matrix]
my-native-pkg = ["ubuntu-latest", "macos-14"]
my-python-pkg = ["ubuntu-latest"]
```

## How it works in CI

Each runner gets its own build job that builds all assigned packages in topological dependency order. The release plan output shows the build layers per runner:

```
  run   build
          ubuntu-latest
            layer 0
              pkg-alpha (0.1.11)
            layer 1
              pkg-beta (0.1.15)
          macos-14
            layer 0
              my-native-pkg (1.2.3)
```
---

**Under the hood:** [Build matrix internals](../under-the-hood/04-build-matrix.md)
