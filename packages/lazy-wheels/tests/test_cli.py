"""Tests for lazy_wheels.cli."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from lazy_wheels.cli import cli


def _write_workspace_repo(root: Path, package_names: list[str]) -> None:
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
    )
    for package_name in package_names:
        package_dir = root / "packages" / package_name
        package_dir.mkdir(parents=True)
        (package_dir / "pyproject.toml").write_text(
            f'[project]\nname = "{package_name}"\nversion = "1.0.0"\n'
        )


class TestInit:
    """Tests for init command."""

    def test_writes_default_release_workflow(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """init writes the default workflow template."""
        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        result = runner.invoke(cli, ["init"], catch_exceptions=False)

        assert result.exit_code == 0
        workflow = tmp_path / ".github" / "workflows" / "release.yml"
        assert workflow.exists()
        assert "jobs:\n  release:" in workflow.read_text()

    def test_matrix_builder_writes_split_jobs_workflow(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """init --matrix-builder creates matrix workflow with selected runners."""
        _write_workspace_repo(tmp_path, ["pkg-alpha", "pkg-beta"])
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        result = runner.invoke(
            cli,
            ["init", "--matrix-builder"],
            input="ubuntu-latest\nubuntu-latest,ubuntu-24.04-arm\n",
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        workflow = (tmp_path / ".github" / "workflows" / "release.yml").read_text()
        assert "jobs:\n  discover:" in workflow
        assert "outputs:\n      changed: ${{ steps.plan.outputs.changed }}" in workflow
        assert '- package: "pkg-beta"' in workflow
        assert 'runner: "ubuntu-24.04-arm"' in workflow
