"""Tests for command execute() methods that call external tools.

Each command is tested with mocked subprocess.run to verify it
constructs the right shell command and handles exit codes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from uv_release.commands.dispatch import DispatchWorkflowCommand
from uv_release.commands.download import (
    DownloadRunArtifactsCommand,
    DownloadWheelsCommand,
)
from uv_release.commands.fetch import (
    FetchSkillBasesCommand,
    FetchWorkflowBaseCommand,
)
from uv_release.commands.publish import PublishToIndexCommand


class TestDispatchWorkflowCommand:
    def test_calls_gh_workflow_run(self) -> None:
        cmd = DispatchWorkflowCommand(label="Dispatch", plan_json='{"jobs":[]}')
        calls: list[list[str]] = []

        def _mock(args, **kwargs):
            calls.append(list(args))
            if args[0] == "git":
                return subprocess.CompletedProcess(args, 0, stdout="main\n")
            return subprocess.CompletedProcess(args, 0, stdout="[]")

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        gh_call = next(c for c in calls if c[0] == "gh")
        assert "workflow" in gh_call
        assert "run" in gh_call
        assert "release.yml" in gh_call

    def test_failure_returns_nonzero(self) -> None:
        cmd = DispatchWorkflowCommand(label="Dispatch", plan_json="{}")

        def _mock(args, **kwargs):
            if args[0] == "git":
                return subprocess.CompletedProcess(args, 0, stdout="main\n")
            return subprocess.CompletedProcess(args, 1)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 1


class TestDownloadWheelsCommand:
    def test_calls_gh_release_download(self) -> None:
        cmd = DownloadWheelsCommand(
            label="Download", tag_name="pkg/v1.0.0", pattern="*.whl", output_dir="dist"
        )
        calls: list[list[str]] = []

        def _mock(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        assert any("gh" in c and "release" in c and "download" in c for c in calls)
        assert any("pkg/v1.0.0" in c for c in calls)

    def test_failure_returns_nonzero(self) -> None:
        cmd = DownloadWheelsCommand(
            label="Download", tag_name="pkg/v1.0.0", pattern="*.whl"
        )

        def _mock(args, **kwargs):
            return subprocess.CompletedProcess(args, 1)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 1


class TestDownloadRunArtifactsCommand:
    def test_calls_gh_run_download(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RUN_ID", "99999")
        out = tmp_path / "dist"
        out.mkdir()
        cmd = DownloadRunArtifactsCommand(label="Download", output_dir=str(out))
        calls: list[list[str]] = []

        def _mock(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        gh_call = next(c for c in calls if c[0] == "gh")
        assert "run" in gh_call
        assert "download" in gh_call
        assert "99999" in gh_call

    def test_no_run_id_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RUN_ID", raising=False)
        cmd = DownloadRunArtifactsCommand(label="Download")
        rc = cmd.execute()
        assert rc == 0

    def test_failure_returns_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RUN_ID", "99999")
        cmd = DownloadRunArtifactsCommand(label="Download")

        def _mock(args, **kwargs):
            return subprocess.CompletedProcess(args, 1)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 1


class TestPublishToIndexCommand:
    def test_calls_uv_publish(self, tmp_path: Path) -> None:
        # Create a fake wheel so the glob finds something.
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "my_pkg-1.0.0-py3-none-any.whl").write_text("")

        cmd = PublishToIndexCommand(
            label="Publish", package_name="my-pkg", dist_dir=str(dist), index="pypi"
        )
        calls: list[list[str]] = []

        def _mock(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        uv_call = next(c for c in calls if c[0] == "uv")
        assert "publish" in uv_call
        assert "--index" in uv_call
        assert "pypi" in uv_call
        assert any(".whl" in arg for arg in uv_call)

    def test_no_wheels_returns_error(self, tmp_path: Path) -> None:
        dist = tmp_path / "dist"
        dist.mkdir()
        cmd = PublishToIndexCommand(
            label="Publish", package_name="my-pkg", dist_dir=str(dist)
        )
        rc = cmd.execute()
        assert rc == 1

    def test_failure_returns_nonzero(self, tmp_path: Path) -> None:
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "my_pkg-1.0.0-py3-none-any.whl").write_text("")
        cmd = PublishToIndexCommand(
            label="Publish", package_name="my-pkg", dist_dir=str(dist)
        )

        def _mock(args, **kwargs):
            return subprocess.CompletedProcess(args, 1)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 1


def _install_template_layout(
    target: Path, *, workflow: str, skills: dict[str, dict[str, str]]
) -> None:
    """Populate target dir with the uv_release template layout used by the fallback."""
    tmpl_root = target / "uv_release" / "templates"
    wf_path = tmpl_root / "release" / "release.yml"
    wf_path.parent.mkdir(parents=True, exist_ok=True)
    wf_path.write_text(workflow, encoding="utf-8")
    skills_root = tmpl_root / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    for skill_name, files in skills.items():
        for rel, content in files.items():
            target_file = skills_root / skill_name / rel
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content, encoding="utf-8")


class TestFetchWorkflowBaseCommand:
    def test_uvx_success_writes_stdout(self, tmp_path: Path) -> None:
        cmd = FetchWorkflowBaseCommand(
            label="Fetch",
            from_version="0.34.0",
            output_path=str(tmp_path / "base.yml"),
        )

        def _mock(args, **kwargs):
            assert args[0] == "uvx"
            return subprocess.CompletedProcess(args, 0, stdout="name: from-uvx\n")

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        assert (tmp_path / "base.yml").read_text() == "name: from-uvx\n"

    def test_falls_back_to_install_on_uvx_failure(self, tmp_path: Path) -> None:
        out_path = tmp_path / "base.yml"
        cmd = FetchWorkflowBaseCommand(
            label="Fetch", from_version="0.33.0", output_path=str(out_path)
        )

        def _mock(args, **kwargs):
            if args[0] == "uvx":
                # Mimic the real bug: inner uvr's provider raises before
                # --print-template can short-circuit.
                return subprocess.CompletedProcess(
                    args, 1, stderr="ERROR: file already exists"
                )
            # `uv pip install --target <tmp> --no-deps uv-release==...`
            assert args[:3] == ["uv", "pip", "install"]
            assert "--target" in args
            target = Path(args[args.index("--target") + 1])
            _install_template_layout(
                target,
                workflow="name: from-fallback\n",
                skills={},
            )
            return subprocess.CompletedProcess(args, 0)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        assert out_path.read_text() == "name: from-fallback\n"

    def test_fallback_install_failure_returns_nonzero(self, tmp_path: Path) -> None:
        cmd = FetchWorkflowBaseCommand(
            label="Fetch",
            from_version="0.33.0",
            output_path=str(tmp_path / "base.yml"),
        )

        def _mock(args, **kwargs):
            if args[0] == "uvx":
                return subprocess.CompletedProcess(args, 1, stderr="boom")
            return subprocess.CompletedProcess(args, 1, stderr="no such version")

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 1


class TestFetchSkillBasesCommand:
    def test_uvx_success_writes_payload(self, tmp_path: Path) -> None:
        import json as _json

        cmd = FetchSkillBasesCommand(
            label="Fetch",
            from_version="0.34.0",
            output_root=str(tmp_path / "bases"),
        )
        payload = {
            "release": [{"rel_path": "SKILL.md", "content": "hello\n"}],
        }

        def _mock(args, **kwargs):
            assert args[0] == "uvx"
            return subprocess.CompletedProcess(args, 0, stdout=_json.dumps(payload))

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        assert (tmp_path / "bases" / "release" / "SKILL.md").read_text() == "hello\n"

    def test_falls_back_to_install_on_uvx_failure(self, tmp_path: Path) -> None:
        out_root = tmp_path / "bases"
        cmd = FetchSkillBasesCommand(
            label="Fetch", from_version="0.33.0", output_root=str(out_root)
        )

        def _mock(args, **kwargs):
            if args[0] == "uvx":
                return subprocess.CompletedProcess(
                    args, 1, stderr="ERROR: skill files already exist"
                )
            assert args[:3] == ["uv", "pip", "install"]
            target = Path(args[args.index("--target") + 1])
            _install_template_layout(
                target,
                workflow="",
                skills={
                    "release": {
                        "SKILL.md": "skill body\n",
                        # Nested references dir must round-trip with posix
                        # path separators in the output rel_path.
                        "references/pipeline.md": "pipeline body\n",
                    },
                },
            )
            return subprocess.CompletedProcess(args, 0)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        assert (out_root / "release" / "SKILL.md").read_text() == "skill body\n"
        assert (
            out_root / "release" / "references" / "pipeline.md"
        ).read_text() == "pipeline body\n"

    def test_falls_back_when_payload_unparseable(self, tmp_path: Path) -> None:
        out_root = tmp_path / "bases"
        cmd = FetchSkillBasesCommand(
            label="Fetch", from_version="0.33.0", output_root=str(out_root)
        )

        def _mock(args, **kwargs):
            if args[0] == "uvx":
                # uvx exits 0 but emits non-JSON (e.g., a prior version with
                # a different --print-template format). Must still fall back.
                return subprocess.CompletedProcess(args, 0, stdout="not json")
            target = Path(args[args.index("--target") + 1])
            _install_template_layout(
                target,
                workflow="",
                skills={"release": {"SKILL.md": "ok\n"}},
            )
            return subprocess.CompletedProcess(args, 0)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 0
        assert (out_root / "release" / "SKILL.md").read_text() == "ok\n"

    def test_fallback_missing_templates_dir_returns_nonzero(
        self, tmp_path: Path
    ) -> None:
        cmd = FetchSkillBasesCommand(
            label="Fetch",
            from_version="0.33.0",
            output_root=str(tmp_path / "bases"),
        )

        def _mock(args, **kwargs):
            if args[0] == "uvx":
                return subprocess.CompletedProcess(args, 1, stderr="boom")
            # Install "succeeds" but writes nothing — the templates dir
            # never appears, so we can't extract anything.
            return subprocess.CompletedProcess(args, 0)

        with patch("subprocess.run", side_effect=_mock):
            rc = cmd.execute()
        assert rc == 1
