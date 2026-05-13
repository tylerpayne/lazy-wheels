from __future__ import annotations

from pathlib import Path

import diny
import pytest

from conftest import git, git_head, read_toml, run_cli, tag_all


class TestVersion:
    @pytest.mark.parametrize(
        "args,expected",
        [
            (["--bump", "major"], "1.0.0.dev0"),
            (["--bump", "minor"], "0.2.0.dev0"),
            (["--bump", "patch"], "0.1.1.dev0"),
            (["--bump", "dev"], "0.1.0.dev1"),
            (["--bump", "stable"], "0.1.0"),
            (["--bump", "alpha"], "0.1.0a0.dev0"),
            (["--bump", "a"], "0.1.0a0.dev0"),
            (["--bump", "beta"], "0.1.0b0.dev0"),
            (["--bump", "b"], "0.1.0b0.dev0"),
            (["--bump", "rc"], "0.1.0rc0.dev0"),
            (["--set", "2.0.0"], "2.0.0"),
        ],
    )
    def test_version_modes(
        self, workspace: Path, args: list[str], expected: str
    ) -> None:
        with diny.provide():
            run_cli("version", *args, "--no-commit", "--no-push")
        ver = read_toml(workspace / "packages" / "pkg-a" / "pyproject.toml")
        assert ver["project"]["version"] == expected

    def test_post_from_dev_errors(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            with diny.provide():
                run_cli("version", "--bump", "post", "--no-commit", "--no-push")
        assert "Cannot bump post" in capsys.readouterr().err

    def test_pins_internal_deps(self, workspace: Path) -> None:
        """Non-dev versions get pinned. --bump stable strips .dev0 -> 0.1.0."""
        with diny.provide():
            run_cli("version", "--bump", "stable", "--no-commit", "--no-push")
        deps = read_toml(workspace / "packages" / "pkg-b" / "pyproject.toml")[
            "project"
        ]["dependencies"]
        assert any("pkg-a>=0.1.0" in str(d) for d in deps)

    def test_dev_bump_skips_pins(self, workspace: Path) -> None:
        """Dev versions should not be pinned because they are not installable from PyPI."""
        with diny.provide():
            run_cli("version", "--bump", "dev", "--no-commit", "--no-push")
        deps = read_toml(workspace / "packages" / "pkg-b" / "pyproject.toml")[
            "project"
        ]["dependencies"]
        # Original dep should be unchanged (dev versions are not pinned).
        assert deps == ["pkg-a>=0.1.0"]

    def test_commits_by_default(self, workspace: Path) -> None:
        with diny.provide():
            run_cli("version", "--bump", "minor", "--no-push")
        log = git(workspace, "log", "--oneline", "-1").stdout
        # Commit message reflects the bump axis (`minor`), not a generic
        # "next dev" string.
        assert "bump minor versions" in log

    def test_no_commit_skips_commit(self, workspace: Path) -> None:
        head_before = git_head(workspace)
        with diny.provide():
            run_cli("version", "--bump", "minor", "--no-commit", "--no-push")
        assert git_head(workspace) == head_before

    def test_packages_flag_limits_scope(self, workspace: Path) -> None:
        with diny.provide():
            run_cli(
                "version",
                "--bump",
                "minor",
                "--no-commit",
                "--no-push",
                "--packages",
                "pkg-a",
            )
        a = read_toml(workspace / "packages" / "pkg-a" / "pyproject.toml")
        b = read_toml(workspace / "packages" / "pkg-b" / "pyproject.toml")
        assert a["project"]["version"] == "0.2.0.dev0"
        assert b["project"]["version"] == "0.1.0.dev0"

    def test_all_packages_flag(self, workspace: Path) -> None:
        tag_all(workspace)
        with diny.provide():
            run_cli(
                "version",
                "--bump",
                "minor",
                "--no-commit",
                "--no-push",
                "--all-packages",
            )
        a = read_toml(workspace / "packages" / "pkg-a" / "pyproject.toml")
        b = read_toml(workspace / "packages" / "pkg-b" / "pyproject.toml")
        assert a["project"]["version"] == "0.2.0.dev0"
        assert b["project"]["version"] == "0.2.0.dev0"

    def test_read_only_shows_versions(
        self, workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with diny.provide():
            run_cli("version")
        out = capsys.readouterr().out
        assert "pkg-a" in out
        assert "0.1.0.dev0" in out
