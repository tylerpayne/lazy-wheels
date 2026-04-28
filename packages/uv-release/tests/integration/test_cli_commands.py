"""Integration tests for CLI commands using real git repos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from uv_release.cli.build import cmd_build
from uv_release.cli.bump import cmd_bump
from uv_release.cli.jobs import cmd_jobs
from uv_release.cli.release import cmd_release
from uv_release.cli.status import cmd_status
from uv_release.cli.workflow import cmd_init_dispatch
from uv_release.cli.skill import cmd_skill_dispatch

from .conftest import _git, add_baseline_tags, modify_file


def _ns(**kwargs: object) -> argparse.Namespace:
    """Build an argparse.Namespace with defaults for extra fields."""
    return argparse.Namespace(**kwargs)


def _write_workflow_with_checks(workspace: Path) -> None:
    """Write a release.yml that has a custom 'checks' job before build and commit it."""
    workflow_dir = workspace / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "release.yml").write_text(
        "name: Release\n"
        "on: workflow_dispatch\n"
        "jobs:\n"
        "  validate:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n"
        "  checks:\n"
        "    needs: [validate]\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n"
        "  build:\n"
        "    needs: [validate, checks]\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n"
        "  release:\n"
        "    needs: [build]\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n"
        "  publish:\n"
        "    needs: [release]\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n"
        "  bump:\n"
        "    needs: [publish]\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n"
    )
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-m", "add release workflow")


def _release_ns(**overrides: object) -> argparse.Namespace:
    """Build a release Namespace with sensible defaults."""
    defaults: dict[str, object] = {
        "where": "local",
        "dry_run": True,
        "plan": None,
        "all_packages": False,
        "packages": None,
        "dev": True,
        "yes": False,
        "skip": None,
        "skip_to": None,
        "reuse_run": None,
        "reuse_release": False,
        "no_push": False,
        "json_output": False,
        "release_notes": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestCmdStatus:
    def test_shows_changed_packages(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_status(_ns(all_packages=False, packages=None))
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out

    def test_shows_unchanged_after_baseline(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        add_baseline_tags(workspace)
        cmd_status(_ns(all_packages=False, packages=None))
        out = capsys.readouterr().out
        assert "unchanged" in out

    def test_all_packages_forces_changed(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        add_baseline_tags(workspace)
        cmd_status(_ns(all_packages=True, packages=None))
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "all packages" in out

    def test_dirty_worktree_warns_not_fails(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (workspace / "dirty.txt").write_text("uncommitted")
        cmd_status(_ns(all_packages=False, packages=None))
        captured = capsys.readouterr()
        assert "WARNING" in captured.err

    def test_nothing_changed_message(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        add_baseline_tags(workspace)
        cmd_status(_ns(all_packages=False, packages=None))
        out = capsys.readouterr().out
        assert "Nothing changed" in out


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


class TestCmdBuild:
    def test_nothing_to_build(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        add_baseline_tags(workspace)
        cmd_build(_ns(all_packages=False, packages=None))
        out = capsys.readouterr().out
        assert "Nothing to build" in out

    def test_shows_packages_to_build(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        add_baseline_tags(workspace)
        modify_file(workspace, "packages/alpha/alpha/__init__.py", "# changed\n")
        # Build will fail (no uv sync in tmp) but we just check the display
        cmd_build(_ns(all_packages=False, packages=None))
        out = capsys.readouterr().out
        assert "Building" in out
        assert "alpha" in out


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------


class TestCmdRelease:
    def test_dry_run_shows_plan(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_release(_release_ns())
        out = capsys.readouterr().out
        assert "Pipeline" in out

    def test_json_output(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_release(_release_ns(json_output=True, dry_run=False))
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "jobs" in parsed

    def test_dirty_worktree_blocks_release(self, workspace: Path) -> None:
        (workspace / "dirty.txt").write_text("uncommitted")
        with pytest.raises((SystemExit, ValueError)):
            cmd_release(_release_ns(dry_run=False))

    def test_nothing_changed(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        add_baseline_tags(workspace)
        cmd_release(_release_ns())
        out = capsys.readouterr().out
        assert "Nothing changed" in out

    def test_nothing_changed_json(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        add_baseline_tags(workspace)
        cmd_release(_release_ns(json_output=True, dry_run=False))
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["jobs"] == []

    def test_plan_from_json(
        self,
        workspace: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # First get a plan JSON
        cmd_release(_release_ns(json_output=True, dry_run=False))
        plan_json = capsys.readouterr().out

        # Now execute it via --plan (decline confirmation to avoid side effects)
        monkeypatch.setattr("builtins.input", lambda _: "n")
        with pytest.raises(SystemExit):
            cmd_release(_release_ns(plan=plan_json, dry_run=False))

    def test_skip_to_skips_preceding_jobs(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_release(_release_ns(skip_to="release"))
        out = capsys.readouterr().out
        assert "skip" in out
        assert "Pipeline" in out

    def test_skip_to_unknown_job_exits(self, workspace: Path) -> None:
        with pytest.raises(SystemExit):
            cmd_release(_release_ns(skip_to="nonexistent-job"))

    def test_skip_to_with_custom_workflow_job(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_workflow_with_checks(workspace)
        cmd_release(_release_ns(skip_to="build", json_output=True, dry_run=False))
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "checks" in parsed["skip"]

    def test_skip_to_targets_custom_job(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_workflow_with_checks(workspace)
        cmd_release(_release_ns(skip_to="checks"))
        out = capsys.readouterr().out
        assert "Pipeline" in out

    def test_skip_to_unknown_job_exits_with_workflow(self, workspace: Path) -> None:
        _write_workflow_with_checks(workspace)
        with pytest.raises(SystemExit):
            cmd_release(_release_ns(skip_to="nonexistent-job"))


# ---------------------------------------------------------------------------
# bump
# ---------------------------------------------------------------------------


class TestCmdBump:
    def test_bump_minor_shows_versions(
        self,
        workspace: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        cmd_bump(
            _ns(
                bump_all=True,
                packages=None,
                force=False,
                no_pin=False,
                bump_type="minor",
            )
        )
        out = capsys.readouterr().out
        assert "1.1.0.dev0" in out

    def test_bump_missing_type_errors(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit, match="1"):
            cmd_bump(
                _ns(
                    bump_all=True,
                    packages=None,
                    force=False,
                    no_pin=False,
                    bump_type="",
                )
            )
        err = capsys.readouterr().err
        assert "Specify a bump type" in err


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------


class TestCmdJobs:
    def test_missing_env_var_exits(self, workspace: Path) -> None:
        with pytest.raises(SystemExit):
            cmd_jobs(_ns(job_name="validate"))

    def test_executes_job_from_env(
        self,
        workspace: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Get a plan JSON (dev_release=True so validate has no confirmation)
        cmd_release(_release_ns(json_output=True, dry_run=False))
        plan_json = capsys.readouterr().out

        monkeypatch.setenv("UVR_PLAN", plan_json)
        # Validate job with dev_release has no commands, runs as no-op
        cmd_jobs(_ns(job_name="validate"))


# ---------------------------------------------------------------------------
# workflow init
# ---------------------------------------------------------------------------


class TestCmdWorkflowInit:
    def test_scaffolds_workflow(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_init_dispatch(
            _ns(
                workflow_dir=".github/workflows",
                force=False,
                upgrade=False,
                base_only=False,
                editor=None,
            )
        )
        out = capsys.readouterr().out
        assert "OK" in out
        assert (workspace / ".github/workflows/release.yml").exists()

    def test_refuses_overwrite_without_force(self, workspace: Path) -> None:
        dest = workspace / ".github/workflows/release.yml"
        dest.parent.mkdir(parents=True)
        dest.write_text("existing")
        with pytest.raises(SystemExit):
            cmd_init_dispatch(
                _ns(
                    workflow_dir=".github/workflows",
                    force=False,
                    upgrade=False,
                    base_only=False,
                    editor=None,
                )
            )

    def test_force_overwrites(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dest = workspace / ".github/workflows/release.yml"
        dest.parent.mkdir(parents=True)
        dest.write_text("old content")
        cmd_init_dispatch(
            _ns(
                workflow_dir=".github/workflows",
                force=True,
                upgrade=False,
                base_only=False,
                editor=None,
            )
        )
        assert dest.read_text() != "old content"

    def test_base_only_writes_merge_base(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_init_dispatch(
            _ns(
                workflow_dir=".github/workflows",
                force=False,
                upgrade=False,
                base_only=True,
                editor=None,
            )
        )
        out = capsys.readouterr().out
        assert "merge base" in out
        assert (workspace / ".uvr/bases/.github/workflows/release.yml").exists()

    def test_upgrade_clean_merge(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # First init
        cmd_init_dispatch(
            _ns(
                workflow_dir=".github/workflows",
                force=False,
                upgrade=False,
                base_only=False,
                editor=None,
            )
        )
        _git(workspace, "add", "-A")
        _git(workspace, "commit", "-m", "add workflow")

        # Upgrade (no changes, should be up to date)
        cmd_init_dispatch(
            _ns(
                workflow_dir=".github/workflows",
                force=False,
                upgrade=True,
                base_only=False,
                editor=None,
            )
        )
        out = capsys.readouterr().out
        assert "up to date" in out


# ---------------------------------------------------------------------------
# skill init
# ---------------------------------------------------------------------------


class TestCmdSkillInit:
    def test_copies_skill_files(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_skill_dispatch(
            _ns(force=False, upgrade=False, base_only=False, editor=None)
        )
        out = capsys.readouterr().out
        assert "OK" in out
        assert (workspace / ".claude/skills/release/SKILL.md").exists()

    def test_skips_existing_without_force(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        skill_dir = workspace / ".claude/skills/release"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("custom")

        cmd_skill_dispatch(
            _ns(force=False, upgrade=False, base_only=False, editor=None)
        )
        # Custom content preserved (not overwritten without --force)
        assert (skill_dir / "SKILL.md").read_text() == "custom"

    def test_force_overwrites(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        skill_dir = workspace / ".claude/skills/release"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("custom")

        cmd_skill_dispatch(_ns(force=True, upgrade=False, base_only=False, editor=None))
        assert (skill_dir / "SKILL.md").read_text() != "custom"

    def test_base_only_writes_merge_bases(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmd_skill_dispatch(_ns(force=False, upgrade=False, base_only=True, editor=None))
        out = capsys.readouterr().out
        assert "merge bases" in out
        assert (workspace / ".uvr/bases/.claude/skills/release/SKILL.md").exists()


# ---------------------------------------------------------------------------
# _upgrade helpers
# ---------------------------------------------------------------------------


class TestUpgradeHelpers:
    def test_write_and_read_base(self, workspace: Path) -> None:
        from uv_release.states.shared.merge_bases import read_merge_base as read_base

        base_file = workspace / ".uvr" / "bases" / "test" / "file.yml"
        base_file.parent.mkdir(parents=True, exist_ok=True)
        base_file.write_text("content")
        assert read_base(workspace, "test/file.yml") == "content"

    def test_read_missing_base(self, workspace: Path) -> None:
        from uv_release.states.shared.merge_bases import read_merge_base as read_base

        assert read_base(workspace, "nonexistent.yml") == ""

    def test_three_way_merge_clean(self, workspace: Path) -> None:
        from uv_release.utils.merge import merge_texts

        current = "line 1\nline 2\n"
        merged, conflicts = merge_texts(current, "line 1\nline 2\n", "line 1\nline 2\n")
        assert not conflicts

    def test_editor_cmd_plain(self) -> None:
        from uv_release.utils.merge import parse_editor_command

        assert parse_editor_command("vim") == ["vim"]

    def test_editor_cmd_gui(self) -> None:
        from uv_release.utils.merge import parse_editor_command

        assert parse_editor_command("code") == ["code", "--wait"]

    def test_resolve_editor_cli_arg(self, workspace: Path) -> None:
        from uv_release.states.uvr_state import _resolve_editor as resolve_editor

        assert resolve_editor("nano") == "nano"

    def test_resolve_editor_env_var(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from uv_release.states.uvr_state import _resolve_editor as resolve_editor

        monkeypatch.setenv("VISUAL", "my-editor")
        assert resolve_editor(None) == "my-editor"
