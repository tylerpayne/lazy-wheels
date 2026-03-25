"""Tests for YAML helpers and the workflow command."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from uv_release_monorepo.cli import (
    _MISSING,
    _yaml_delete,
    _yaml_get,
    _yaml_set,
    cmd_workflow,
)

from tests._helpers import _init_workflow, _wf_args


# ---------------------------------------------------------------------------
# YAML helpers: _yaml_get, _yaml_set, _yaml_delete
# ---------------------------------------------------------------------------


class TestYamlGet:
    def test_shallow(self) -> None:
        assert _yaml_get({"a": 1}, ["a"]) == 1

    def test_nested(self) -> None:
        assert _yaml_get({"a": {"b": {"c": 3}}}, ["a", "b", "c"]) == 3

    def test_missing_key(self) -> None:
        assert _yaml_get({"a": 1}, ["b"]) is _MISSING

    def test_missing_nested(self) -> None:
        assert _yaml_get({"a": {"b": 1}}, ["a", "x"]) is _MISSING

    def test_empty_path(self) -> None:
        doc = {"a": 1}
        assert _yaml_get(doc, []) is doc

    def test_returns_dict(self) -> None:
        assert _yaml_get({"a": {"b": 1}}, ["a"]) == {"b": 1}

    def test_returns_list(self) -> None:
        assert _yaml_get({"a": [1, 2]}, ["a"]) == [1, 2]


class TestYamlSet:
    def test_shallow(self) -> None:
        doc: dict = {}
        _yaml_set(doc, ["a"], 1)
        assert doc == {"a": 1}

    def test_nested_creates_intermediates(self) -> None:
        doc: dict = {}
        _yaml_set(doc, ["a", "b", "c"], 3)
        assert doc == {"a": {"b": {"c": 3}}}

    def test_overwrites_existing(self) -> None:
        doc = {"a": 1}
        _yaml_set(doc, ["a"], 2)
        assert doc == {"a": 2}

    def test_deep_overwrite(self) -> None:
        doc = {"a": {"b": {"c": "old"}}}
        _yaml_set(doc, ["a", "b", "c"], "new")
        assert doc["a"]["b"]["c"] == "new"

    def test_creates_intermediate_over_non_dict(self) -> None:
        doc = {"a": "scalar"}
        _yaml_set(doc, ["a", "b"], 1)
        assert doc == {"a": {"b": 1}}

    def test_set_list(self) -> None:
        doc: dict = {}
        _yaml_set(doc, ["items"], [1, 2, 3])
        assert doc == {"items": [1, 2, 3]}


class TestYamlDelete:
    def test_shallow(self) -> None:
        doc = {"a": 1, "b": 2}
        assert _yaml_delete(doc, ["a"]) is True
        assert doc == {"b": 2}

    def test_nested(self) -> None:
        doc = {"a": {"b": 1, "c": 2}}
        assert _yaml_delete(doc, ["a", "b"]) is True
        assert doc == {"a": {"c": 2}}

    def test_missing_returns_false(self) -> None:
        doc = {"a": 1}
        assert _yaml_delete(doc, ["b"]) is False
        assert doc == {"a": 1}

    def test_missing_nested_returns_false(self) -> None:
        doc = {"a": {"b": 1}}
        assert _yaml_delete(doc, ["a", "x"]) is False

    def test_missing_parent_returns_false(self) -> None:
        doc = {"a": 1}
        assert _yaml_delete(doc, ["x", "y"]) is False


# ---------------------------------------------------------------------------
# cmd_workflow integration tests
# ---------------------------------------------------------------------------


class TestCmdWorkflowRead:
    def test_read_permissions(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_workflow(_wf_args(path=["permissions"], set_value=None))
        out = capsys.readouterr().out
        assert "contents" in out

    def test_read_missing_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_workflow(_wf_args(path=["nonexistent"], set_value=None))
        out = capsys.readouterr().out
        assert "not found" in out

    def test_read_no_path_dumps_doc(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_workflow(_wf_args(path=[], set_value=None))
        out = capsys.readouterr().out
        assert "jobs:" in out


class TestCmdWorkflowSet:
    def test_set_scalar(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_workflow(_wf_args(path=["permissions", "id-token"], set_value="write"))
        cmd_workflow(_wf_args(path=["permissions", "id-token"]))
        out = capsys.readouterr().out
        assert "write" in out

    def test_set_creates_intermediates(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_workflow(_wf_args(path=["jobs", "build", "environment"], set_value="prod"))
        cmd_workflow(_wf_args(path=["jobs", "build", "environment"]))
        out = capsys.readouterr().out
        assert "prod" in out

    def test_set_rejects_invalid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        with pytest.raises(SystemExit):
            cmd_workflow(
                _wf_args(path=["jobs", "bogus"], set_value="{runs-on: ubuntu}")
            )


class TestCmdWorkflowClear:
    def test_clear_existing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_workflow(_wf_args(path=["permissions", "id-token"], set_value="write"))
        capsys.readouterr()
        cmd_workflow(_wf_args(path=["permissions", "id-token"], clear=True))
        out = capsys.readouterr().out
        assert "Deleted" in out

    def test_clear_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_workflow(_wf_args(path=["permissions", "nope"], clear=True))
        out = capsys.readouterr().out
        assert "not found" in out


class TestCmdWorkflowList:
    def test_add_creates_list(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="release"))
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"]))
        out = capsys.readouterr().out
        assert "release" in out

    def test_add_appends(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        capsys.readouterr()
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="a"))
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="b"))
        doc = yaml.safe_load(release_yml.read_text())
        assert doc["jobs"]["build"]["tags"] == ["a", "b"]

    def test_add_to_non_list_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        with pytest.raises(SystemExit):
            cmd_workflow(_wf_args(path=["permissions", "contents"], add_value="read"))

    def test_insert_at_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="a"))
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="c"))
        cmd_workflow(
            _wf_args(path=["jobs", "build", "tags"], insert_value="b", insert_index=1)
        )
        doc = yaml.safe_load(release_yml.read_text())
        assert doc["jobs"]["build"]["tags"] == ["a", "b", "c"]

    def test_insert_negative_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="a"))
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="c"))
        cmd_workflow(
            _wf_args(path=["jobs", "build", "tags"], insert_value="b", insert_index=-1)
        )
        doc = yaml.safe_load(release_yml.read_text())
        assert doc["jobs"]["build"]["tags"] == ["a", "b", "c"]

    def test_insert_requires_at(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="a"))
        with pytest.raises(SystemExit):
            cmd_workflow(_wf_args(path=["jobs", "build", "tags"], insert_value="b"))

    def test_remove(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        release_yml = _init_workflow(tmp_path, monkeypatch)
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="a"))
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="b"))
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], remove_value="a"))
        doc = yaml.safe_load(release_yml.read_text())
        assert doc["jobs"]["build"]["tags"] == ["b"]

    def test_remove_missing_value_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_workflow(tmp_path, monkeypatch)
        cmd_workflow(_wf_args(path=["jobs", "build", "tags"], add_value="a"))
        with pytest.raises(SystemExit):
            cmd_workflow(_wf_args(path=["jobs", "build", "tags"], remove_value="z"))
