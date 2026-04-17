"""Load user hooks from the workspace."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import tomlkit
from pydantic import BaseModel, ConfigDict

from ..types import Hooks


# ---------------------------------------------------------------------------
# Pydantic models for pyproject.toml hooks section
# ---------------------------------------------------------------------------


class _UvrHooks(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    file: str = ""


class _Uvr(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    hooks: _UvrHooks = _UvrHooks()


class _Tool(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    uvr: _Uvr = _Uvr()


class _HooksPyProject(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    tool: _Tool = _Tool()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_hooks() -> Hooks | None:
    """Read hooks configuration from the root pyproject.toml and load them.

    This is intentionally independent of parse_workspace so that hooks
    can be loaded before the full workspace is parsed.
    """
    root = Path.cwd()
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        return None

    doc = tomlkit.loads(pyproject_path.read_text())
    pyproject = _HooksPyProject.model_validate(doc)

    if pyproject.tool.uvr.hooks.file:
        return _load_from_spec(root, pyproject.tool.uvr.hooks.file)

    fallback = root / Hooks.DEFAULT_FILE
    if fallback.exists():
        return _load_from_spec(root, f"{Hooks.DEFAULT_FILE}:{Hooks.DEFAULT_CLASS}")

    return None


def _load_from_spec(root: Path, spec: str) -> Hooks:
    """Load a hook class from a 'path:ClassName' spec."""
    if ":" in spec:
        file_path, class_name = spec.rsplit(":", 1)
    else:
        file_path = spec
        class_name = Hooks.DEFAULT_CLASS

    full_path = root / file_path
    if not full_path.exists():
        msg = f"Hook file not found: {full_path}"
        raise FileNotFoundError(msg)

    module_spec = importlib.util.spec_from_file_location("_uvr_hooks", full_path)
    if module_spec is None or module_spec.loader is None:
        msg = f"Cannot load hook module: {full_path}"
        raise ImportError(msg)

    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    hook_class = getattr(module, class_name, None)
    if hook_class is None:
        msg = f"Hook class {class_name!r} not found in {full_path}"
        raise AttributeError(msg)

    return hook_class()
