"""Project-level uvr configuration parsed from pyproject.toml."""

from __future__ import annotations

import os
import shutil
from importlib.metadata import version as pkg_version
from pathlib import Path

import tomlkit

from ..types import Config, Publishing, RootPyProject
from .base import State

_FALLBACK_EDITORS = ("code", "vim", "vi", "nano")


class UvrState(State):
    """Project-level uvr configuration parsed from pyproject.toml."""

    config: Config
    publishing: Publishing
    runners: dict[str, list[list[str]]]
    editor: str | None = None
    uvr_version: str = ""

    @classmethod
    def parse(cls) -> UvrState:
        """Read uvr configuration from the root pyproject.toml."""
        root = Path.cwd()
        doc = tomlkit.loads((root / "pyproject.toml").read_text())
        root_pyproject = RootPyProject.model_validate(doc)

        uvr = root_pyproject.tool.uvr

        uvr_version = _read_uvr_version()

        config = Config(
            uvr_version=uvr_version,
            latest_package=uvr.config.latest,
            python_version=uvr.config.python_version,
            include=frozenset(uvr.config.include),
            exclude=frozenset(uvr.config.exclude),
        )

        runners = dict(uvr.runners)

        publishing = Publishing(
            index=uvr.publish.index,
            environment=uvr.publish.environment,
            trusted_publishing=uvr.publish.trusted_publishing,
            include=frozenset(uvr.publish.include),
            exclude=frozenset(uvr.publish.exclude),
        )

        editor = _resolve_editor(None)

        return UvrState(
            config=config,
            publishing=publishing,
            runners=runners,
            editor=editor,
            uvr_version=uvr_version,
        )


def _read_uvr_version() -> str:
    """Read the version of this uv_release package from installed metadata."""
    return pkg_version("uv_release")


def _resolve_editor(cli_editor: str | None) -> str | None:
    """Resolve editor: CLI arg > $VISUAL > $EDITOR > fallback."""
    if cli_editor:
        return cli_editor

    env_editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if env_editor:
        return env_editor

    for name in _FALLBACK_EDITORS:
        if shutil.which(name):
            return name

    return None
