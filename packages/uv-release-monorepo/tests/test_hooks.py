"""Tests for the hooks command (CRUD wrapper over workflow engine)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from uv_release_monorepo.cli import cmd_hooks
from uv_release_monorepo.cli.workflow import _STDIN

from tests._helpers import _hooks_args, _init_workflow


class TestCmdHooksRead:
    def test_read_entire_job(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_hooks(_hooks_args("pre-build"))
        out = capsys.readouterr().out
        # Should dump the pre-build job (may have steps or be a simple dict)
        assert "steps" in out or "runs-on" in out or "not found" in out

    def test_read_steps(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_hooks(_hooks_args("pre-build", path=".steps"))
        out = capsys.readouterr().out
        # Steps is a list — either content or some output
        assert out.strip()

    def test_read_environment(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        # First set an environment, then read it
        cmd_hooks(_hooks_args("post-release", path=".environment", set_value="pypi"))
        capsys.readouterr()
        cmd_hooks(_hooks_args("post-release", path=".environment"))
        out = capsys.readouterr().out
        assert "pypi" in out


class TestCmdHooksSet:
    def test_set_environment(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_hooks(_hooks_args("post-release", path=".environment", set_value="pypi"))
        out = capsys.readouterr().out
        assert "Set" in out
        doc = yaml.safe_load(release_yml.read_text())
        assert doc["jobs"]["post-release"]["environment"] == "pypi"


class TestCmdHooksAppend:
    def test_append_step(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                append_value="{name: Test, run: pytest}",
            )
        )
        out = capsys.readouterr().out
        assert "Appended" in out
        doc = yaml.safe_load(release_yml.read_text())
        steps = doc["jobs"]["pre-build"]["steps"]
        # Find our appended step (after the template steps)
        names = [s.get("name") for s in steps if isinstance(s, dict)]
        assert "Test" in names

    def test_append_multiple_steps(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                append_value="{name: Lint, run: ruff check}",
            )
        )
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                append_value="{name: Test, run: pytest}",
            )
        )
        doc = yaml.safe_load(release_yml.read_text())
        steps = doc["jobs"]["pre-build"]["steps"]
        names = [s.get("name") for s in steps if isinstance(s, dict)]
        assert "Lint" in names
        assert "Test" in names


class TestCmdHooksInsert:
    def test_insert_step(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        # Append two steps, then insert one at index 0
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                append_value="{name: Second, run: echo second}",
            )
        )
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                insert_value="{name: First, run: echo first}",
                at_index=0,
            )
        )
        doc = yaml.safe_load(release_yml.read_text())
        steps = doc["jobs"]["pre-build"]["steps"]
        assert steps[0]["name"] == "First"

    def test_insert_requires_at(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        with pytest.raises(SystemExit):
            cmd_hooks(
                _hooks_args(
                    "pre-build",
                    path=".steps",
                    insert_value="{name: Oops, run: echo oops}",
                )
            )


class TestCmdHooksRemove:
    def test_remove_by_index(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                append_value="{name: A, run: echo a}",
            )
        )
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                append_value="{name: B, run: echo b}",
            )
        )
        doc = yaml.safe_load(release_yml.read_text())
        initial_count = len(doc["jobs"]["pre-build"]["steps"])

        # Remove the last step (our "B") by index
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                remove_value=_STDIN,
                at_index=initial_count - 1,
            )
        )
        doc = yaml.safe_load(release_yml.read_text())
        assert len(doc["jobs"]["pre-build"]["steps"]) == initial_count - 1


class TestCmdHooksClear:
    def test_clear_steps(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                append_value="{name: Test, run: pytest}",
            )
        )
        capsys.readouterr()
        cmd_hooks(_hooks_args("pre-build", path=".steps", clear=True))
        out = capsys.readouterr().out
        assert "Cleared" in out
        doc = yaml.safe_load(release_yml.read_text())
        # Clear resets to the no-op default (steps can never be empty)
        steps = doc["jobs"]["pre-build"]["steps"]
        assert len(steps) == 1
        assert steps[0]["name"] == "Never"


class TestCmdHooksNestedAccess:
    def test_read_step_name(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                append_value="{name: MyStep, run: echo hi}",
            )
        )
        capsys.readouterr()
        # Read the last step's name — find its index first
        doc = yaml.safe_load(
            (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        )
        last_idx = len(doc["jobs"]["pre-build"]["steps"]) - 1
        cmd_hooks(_hooks_args("pre-build", path=f".steps.{last_idx}.name"))
        out = capsys.readouterr().out
        assert "MyStep" in out

    def test_set_step_name(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=".steps",
                append_value="{name: OldName, run: echo hi}",
            )
        )
        doc = yaml.safe_load(release_yml.read_text())
        last_idx = len(doc["jobs"]["pre-build"]["steps"]) - 1
        cmd_hooks(
            _hooks_args(
                "pre-build",
                path=f".steps.{last_idx}.name",
                set_value="NewName",
            )
        )
        doc = yaml.safe_load(release_yml.read_text())
        assert doc["jobs"]["pre-build"]["steps"][last_idx]["name"] == "NewName"
