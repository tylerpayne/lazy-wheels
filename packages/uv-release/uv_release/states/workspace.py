"""Parse the workspace from the filesystem into a frozen Workspace."""

from __future__ import annotations

from pathlib import Path

import tomlkit

from ..types import Config, Package, Publishing, RootPyProject, Workspace
from .package import parse_package


def parse_workspace() -> Workspace:
    """Read the workspace root and all package directories."""
    root = Path.cwd()
    doc = tomlkit.loads((root / "pyproject.toml").read_text())
    root_pyproject = RootPyProject.model_validate(doc)

    uvr = root_pyproject.tool.uvr

    # Discover package directories
    package_dirs: list[Path] = []
    for pattern in root_pyproject.tool.uv.workspace.members:
        package_dirs.extend(sorted(root.glob(pattern)))

    # First pass: collect member names for dep filtering
    member_names: set[str] = set()
    for pkg_dir in package_dirs:
        if not (pkg_dir / "pyproject.toml").exists():
            continue
        pkg_doc = tomlkit.loads((pkg_dir / "pyproject.toml").read_text())
        name = pkg_doc.get("project", {}).get("name")
        if name:
            member_names.add(name)

    workspace_members = frozenset(member_names)

    # Second pass: build packages
    packages: dict[str, Package] = {}
    for pkg_dir in package_dirs:
        if not (pkg_dir / "pyproject.toml").exists():
            continue
        pkg = parse_package(pkg_dir, workspace_members=workspace_members)
        packages[pkg.name] = pkg

    # Build config
    config = Config(
        uvr_version=read_uvr_version(),
        latest_package=uvr.config.latest,
        python_version=uvr.config.python_version,
        include=frozenset(uvr.config.include),
        exclude=frozenset(uvr.config.exclude),
    )

    # Build runners
    runners = dict(uvr.runners)

    # Build publishing
    publishing = Publishing(
        index=uvr.publish.index,
        environment=uvr.publish.environment,
        trusted_publishing=uvr.publish.trusted_publishing,
        include=frozenset(uvr.publish.include),
        exclude=frozenset(uvr.publish.exclude),
    )

    # Apply include/exclude filtering
    if config.include:
        packages = {n: p for n, p in packages.items() if n in config.include}
    if config.exclude:
        packages = {n: p for n, p in packages.items() if n not in config.exclude}

    return Workspace(
        packages=packages,
        config=config,
        runners=runners,
        publishing=publishing,
    )


def read_uvr_version() -> str:
    """Read the version of this uv_release package from installed metadata."""
    from importlib.metadata import version

    return version("uv_release")
