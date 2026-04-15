"""Tests for hook loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.parse.hooks import _load_from_spec, parse_hooks


class TestParseHooks:
    def test_no_pyproject_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert parse_hooks() is None

    def test_configured_hook_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.uvr.hooks]\nfile = "my_hooks.py:MyHook"\n'
        )
        (tmp_path / "my_hooks.py").write_text(
            "from uv_release.types import Hooks\nclass MyHook(Hooks): pass\n"
        )
        result = parse_hooks()
        assert result is not None

    def test_fallback_default_hook_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        (tmp_path / "uvr_hooks.py").write_text(
            "from uv_release.types import Hooks\nclass Hooks(Hooks): pass\n"
        )
        result = parse_hooks()
        assert result is not None


class TestLoadHooks:
    def test_loads_from_spec(self, tmp_path: Path) -> None:
        hook_file = tmp_path / "my_hooks.py"
        hook_file.write_text(
            "from uv_release.types import Hooks\nclass MyHook(Hooks): pass\n"
        )
        result = _load_from_spec(tmp_path, "my_hooks.py:MyHook")
        assert result is not None

    def test_fallback_class_name(self, tmp_path: Path) -> None:
        hook_file = tmp_path / "uvr_hooks.py"
        hook_file.write_text(
            "from uv_release.types import Hooks\nclass Hook(Hooks): pass\n"
        )
        result = _load_from_spec(tmp_path, "uvr_hooks.py")
        assert result is not None

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _load_from_spec(tmp_path, "nonexistent.py:Hook")

    def test_missing_class_raises(self, tmp_path: Path) -> None:
        hook_file = tmp_path / "hooks.py"
        hook_file.write_text("class Other: pass\n")
        with pytest.raises(AttributeError):
            _load_from_spec(tmp_path, "hooks.py:Missing")

    def test_non_python_file_raises_import_error(self, tmp_path: Path) -> None:
        hook_file = tmp_path / "hooks.txt"
        hook_file.write_text("not python")
        with pytest.raises(ImportError):
            _load_from_spec(tmp_path, "hooks.txt:Hook")
