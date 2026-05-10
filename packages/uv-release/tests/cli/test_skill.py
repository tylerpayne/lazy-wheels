from __future__ import annotations

import json
from pathlib import Path

import diny
import pytest

from conftest import run_cli


class TestSkillUpgrade:
    def test_scaffolds_skill_files(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with diny.provide():
            run_cli("skill", "install")
        out = capsys.readouterr().out
        assert "Create" in out or "skill-upgrade" in out
        # Skill files should now exist in the workspace.
        skills_dir = workspace / ".claude" / "skills"
        assert skills_dir.exists()

    def test_print_template_with_existing_files(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Scaffold first so skill files exist in cwd.
        with diny.provide():
            run_cli("skill", "install")
        assert (workspace / ".claude" / "skills").exists()
        capsys.readouterr()
        # --print-template must short-circuit even when files exist and no
        # --upgrade/--force flag is passed. The buggy provider previously
        # raised "Skill files already exist..." breaking the uvx fetch path.
        with diny.provide():
            run_cli("skill", "install", "--print-template")
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload, "expected at least one bundled skill"
        for files in payload.values():
            assert files and "rel_path" in files[0] and "content" in files[0]
