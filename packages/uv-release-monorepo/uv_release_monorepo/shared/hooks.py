"""Hook system for the release pipeline.

Hooks are Python classes that can transform the release plan at defined
points in the pipeline.  Users subclass :class:`ReleaseHook` and override
the methods they care about.

Discovery order:

1. ``[tool.uvr.hooks] file = "path:ClassName"`` in the root ``pyproject.toml``
2. Convention file ``uvr_hooks.py`` at the workspace root with class ``Hook``

Hook points
-----------

**Local** (run during ``uvr release`` on the developer's machine):

- :meth:`~ReleaseHook.pre_plan` — before plan generation
- :meth:`~ReleaseHook.post_plan` — after plan generation

**CI** (run during executor phases — build / publish / finalize):

- :meth:`~ReleaseHook.pre_build` / :meth:`~ReleaseHook.post_build`
- :meth:`~ReleaseHook.pre_release` / :meth:`~ReleaseHook.post_release`
- :meth:`~ReleaseHook.pre_finalize` / :meth:`~ReleaseHook.post_finalize`
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .models import PlanConfig, ReleasePlan


class ReleaseHook:
    """Base class for release hooks.  Override methods to customise."""

    # -- local hooks -------------------------------------------------------

    def pre_plan(self, config: PlanConfig) -> PlanConfig:
        """Called before plan generation.  Return a (possibly modified) config."""
        return config

    def post_plan(self, plan: ReleasePlan) -> ReleasePlan:
        """Called after plan generation.  Return a (possibly modified) plan."""
        return plan

    # -- CI hooks ----------------------------------------------------------

    def pre_build(self, plan: ReleasePlan, runner: list[str] | None = None) -> None:
        """Called before the build phase."""

    def post_build(self, plan: ReleasePlan, runner: list[str] | None = None) -> None:
        """Called after the build phase."""

    def pre_build_stage(
        self,
        plan: ReleasePlan,
        packages: list[str],
        runner: list[str] | None = None,
    ) -> None:
        """Called before each build stage with the packages about to be built."""

    def post_build_stage(
        self,
        plan: ReleasePlan,
        packages: list[str],
        runner: list[str] | None = None,
    ) -> None:
        """Called after each build stage with the packages that were built."""

    def pre_build_package(self, plan: ReleasePlan, package: str) -> None:
        """Called before building a single package (may run in parallel)."""

    def post_build_package(self, plan: ReleasePlan, package: str) -> None:
        """Called after building a single package (may run in parallel)."""

    def pre_release(self, plan: ReleasePlan) -> None:
        """Called before the publish/release phase."""

    def post_release(self, plan: ReleasePlan) -> None:
        """Called after the publish/release phase."""

    def pre_finalize(self, plan: ReleasePlan) -> None:
        """Called before the finalize phase."""

    def post_finalize(self, plan: ReleasePlan) -> None:
        """Called after the finalize phase."""


# Default convention file name and class name
_CONVENTION_FILE = "uvr_hooks.py"
_DEFAULT_CLASS = "Hook"


def _import_class_from_file(file_path: Path, class_name: str) -> type[ReleaseHook]:
    """Dynamically import *class_name* from *file_path*."""
    spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
    if spec is None or spec.loader is None:
        print(
            f"Error: cannot load hook module: {file_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        print(
            f"Error: failed to execute hook module {file_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    cls = getattr(module, class_name, None)
    if cls is None:
        print(
            f"Error: hook module {file_path} has no class '{class_name}'",
            file=sys.stderr,
        )
        sys.exit(1)

    if not (isinstance(cls, type) and issubclass(cls, ReleaseHook)):
        print(
            f"Error: {file_path}:{class_name} is not a ReleaseHook subclass",
            file=sys.stderr,
        )
        sys.exit(1)

    return cls


def load_hook(
    root: Path,
    hooks_config: dict[str, str] | None = None,
) -> ReleaseHook | None:
    """Load the user's hook class, or return ``None`` if none is configured.

    Parameters
    ----------
    root:
        Workspace root directory.
    hooks_config:
        The dict returned by :func:`~.toml.get_uvr_hooks`.  When ``None``
        the config is read from the root ``pyproject.toml``.
    """
    if hooks_config is None:
        from .config import get_uvr_hooks
        from .toml import load_pyproject

        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            hooks_config = get_uvr_hooks(load_pyproject(pyproject))
        else:
            hooks_config = {}

    file_spec = hooks_config.get("file", "")

    if file_spec:
        # Explicit config: "path/to/file.py:ClassName" or "path/to/file.py"
        if ":" in file_spec:
            path_str, class_name = file_spec.rsplit(":", 1)
        else:
            path_str, class_name = file_spec, _DEFAULT_CLASS

        file_path = root / path_str
        if not file_path.is_file():
            print(
                f"Error: hook file not found: {file_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        cls = _import_class_from_file(file_path, class_name)
        return cls()

    # Convention discovery
    convention = root / _CONVENTION_FILE
    if convention.is_file():
        cls = _import_class_from_file(convention, _DEFAULT_CLASS)
        return cls()

    return None
