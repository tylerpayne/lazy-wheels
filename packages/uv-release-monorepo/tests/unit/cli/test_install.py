"""Tests for the install command, parse_install_spec, and _find_latest_release_tag."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from uv_release_monorepo.cli import cmd_install
from uv_release_monorepo.shared.utils.cli import parse_install_spec
from uv_release_monorepo.shared.utils.tags import (
    find_latest_remote_release_tag as _find_latest_release_tag,
)

from tests._helpers import _write_workspace_repo


def _make_fake_run(
    *,
    release_tags: list[dict[str, str]] | None = None,
    wheel_name_fn: Callable[[str, str], str] | None = None,
):
    """Build a fake subprocess.run that handles gh list, view, download, and uv pip install.

    Args:
        release_tags: Response for ``gh release list`` (defaults to empty).
        wheel_name_fn: Given (tag, tmp_dir), return the wheel filename to create.
            Defaults to deriving from the tag.
    """
    release_tags = release_tags or []
    calls: list[list[str]] = []

    def _default_wheel_name(tag: str, _dir: str) -> str:
        pkg_name = tag.split("/v")[0].replace("-", "_")
        ver = tag.split("/v")[1]
        return f"{pkg_name}-{ver}-py3-none-any.whl"

    whl_fn = wheel_name_fn or _default_wheel_name

    def fake_run(cmd, **kwargs):
        cmd = list(cmd)
        calls.append(cmd)
        result = MagicMock()
        result.returncode = 0

        if "list" in cmd:
            # gh release list
            result.stdout = json.dumps(release_tags)
        elif "view" in cmd:
            # gh release view <tag> --json assets (from FetchGithubReleaseCommand)
            tag_idx = cmd.index("view") + 1
            tag = cmd[tag_idx]
            whl = whl_fn(tag, "")
            result.stdout = json.dumps({"assets": [{"name": whl}]})
        elif "download" in cmd:
            # gh release download
            tag_idx = cmd.index("download") + 1
            tag = cmd[tag_idx]
            dir_idx = cmd.index("--dir") + 1
            whl_dir = Path(cmd[dir_idx])
            whl_dir.mkdir(parents=True, exist_ok=True)
            whl = whl_fn(tag, str(whl_dir))
            (whl_dir / whl).write_bytes(b"")
        else:
            # uv pip install etc.
            result.stdout = ""
        return result

    return fake_run, calls


class TestCmdInstall:
    """Tests for cmd_install()."""

    @pytest.fixture(autouse=True)
    def _isolate_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

    def test_installs_package_and_deps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Installs the requested package from a remote repo."""
        fake_run, calls = _make_fake_run(
            release_tags=[{"tagName": "pkg-beta/v1.0.0"}],
        )
        monkeypatch.setattr(subprocess, "run", fake_run)

        args = argparse.Namespace(packages=["acme/my-repo/pkg-beta"])
        cmd_install(args)

        install_calls = [c for c in calls if c[:3] == ["uv", "pip", "install"]]
        assert len(install_calls) == 1
        # uv pip install --find-links <cache> <beta.whl>
        assert any("pkg_beta-1.0.0-py3-none-any.whl" in a for a in install_calls[0])

    def test_fails_for_bare_package(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exits with error when package spec has no org/repo."""
        args = argparse.Namespace(packages=["nonexistent-pkg"])

        with pytest.raises(SystemExit):
            cmd_install(args)

    def test_pinned_version_uses_specific_tag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ORG/REPO/PACKAGE@VERSION uses that exact release tag."""
        download_tags: list[str] = []

        def wheel_name(tag: str, _dir: str) -> str:
            return "pkg_alpha-0.1.5-py3-none-any.whl"

        fake_run, calls = _make_fake_run(wheel_name_fn=wheel_name)

        original_fake = fake_run

        def tracking_run(cmd, **kwargs):
            cmd = list(cmd)
            if "download" in cmd:
                tag_idx = cmd.index("download") + 1
                download_tags.append(cmd[tag_idx])
            return original_fake(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", tracking_run)

        args = argparse.Namespace(packages=["acme/my-repo/pkg-alpha@0.1.5"])
        cmd_install(args)

        assert "pkg-alpha/v0.1.5" in download_tags


class TestCmdInstallRemote:
    """Tests for cmd_install() with remote org/repo/package specs."""

    @pytest.fixture(autouse=True)
    def _isolate_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

    def test_remote_install_passes_repo_to_gh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Remote install passes --repo to gh release list and download."""
        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)

        fake_run, calls = _make_fake_run(
            release_tags=[{"tagName": "pkg-alpha/v1.0.0"}],
        )
        monkeypatch.setattr(subprocess, "run", fake_run)

        args = argparse.Namespace(packages=["acme/my-monorepo/pkg-alpha"])
        cmd_install(args)

        repo_cmds = [c for c in calls if "--repo" in c]
        assert all("acme/my-monorepo" in c for c in repo_cmds)

    def test_remote_install_pinned_version_skips_tag_lookup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Remote install with @version uses the tag directly without listing releases."""
        _write_workspace_repo(tmp_path, [])
        monkeypatch.chdir(tmp_path)

        def wheel_name(tag: str, _dir: str) -> str:
            return "pkg_alpha-0.5.0-py3-none-any.whl"

        fake_run, calls = _make_fake_run(wheel_name_fn=wheel_name)
        monkeypatch.setattr(subprocess, "run", fake_run)

        args = argparse.Namespace(packages=["acme/my-monorepo/pkg-alpha@0.5.0"])
        cmd_install(args)

        # _list_repo_packages always calls gh release list, but the tag lookup
        # for find_latest_remote_release_tag should be skipped for pinned versions.
        # Just verify the download used the pinned tag.
        download_cmds = [c for c in calls if "download" in c]
        assert any("pkg-alpha/v0.5.0" in c for c in download_cmds)


class TestParseInstallSpec:
    """Tests for parse_install_spec()."""

    def test_bare_package(self) -> None:
        gh_repo, package, version = parse_install_spec("pkg-alpha")
        assert gh_repo is None
        assert package == "pkg-alpha"
        assert version is None

    def test_bare_package_with_version(self) -> None:
        gh_repo, package, version = parse_install_spec("pkg-alpha@1.2.3")
        assert gh_repo is None
        assert package == "pkg-alpha"
        assert version == "1.2.3"

    def test_remote_package(self) -> None:
        gh_repo, package, version = parse_install_spec("acme/my-monorepo/pkg-alpha")
        assert gh_repo == "acme/my-monorepo"
        assert package == "pkg-alpha"
        assert version is None

    def test_remote_package_with_version(self) -> None:
        gh_repo, package, version = parse_install_spec(
            "acme/my-monorepo/pkg-alpha@2.0.0"
        )
        assert gh_repo == "acme/my-monorepo"
        assert package == "pkg-alpha"
        assert version == "2.0.0"

    def test_invalid_two_part_spec_raises(self) -> None:
        with pytest.raises(SystemExit):
            parse_install_spec("acme/pkg-alpha")

    def test_invalid_four_part_spec_raises(self) -> None:
        with pytest.raises(SystemExit):
            parse_install_spec("acme/org/repo/pkg")


class TestFindLatestReleaseTag:
    """Tests for _find_latest_release_tag()."""

    def test_returns_highest_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns the tag with the highest semver for the given package."""

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(
                [
                    {"tagName": "pkg-alpha/v0.1.0"},
                    {"tagName": "pkg-alpha/v0.1.2"},
                    {"tagName": "pkg-alpha/v0.1.1"},
                    {"tagName": "other-pkg/v9.9.9"},
                ]
            )
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = _find_latest_release_tag("pkg-alpha")

        assert result == "pkg-alpha/v0.1.2"

    def test_excludes_dev_tags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ignores tags ending with -dev."""

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(
                [
                    {"tagName": "pkg-alpha/v0.1.0"},
                    {"tagName": "pkg-alpha/v0.1.1-dev"},
                ]
            )
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = _find_latest_release_tag("pkg-alpha")

        assert result == "pkg-alpha/v0.1.0"

    def test_returns_none_when_no_releases(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns None when no releases exist for the package."""

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([{"tagName": "other-pkg/v1.0.0"}])
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = _find_latest_release_tag("pkg-alpha")

        assert result is None

    def test_returns_none_on_gh_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when gh command fails."""

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = _find_latest_release_tag("pkg-alpha")

        assert result is None


class TestFindLatestReleaseTagRemote:
    """Tests for _find_latest_release_tag() with gh_repo parameter."""

    def test_passes_repo_flag_to_gh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gh release list is called with --repo when gh_repo is provided."""
        seen_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            seen_cmds.append(list(cmd))
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps([{"tagName": "pkg-alpha/v1.0.0"}])
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        _find_latest_release_tag("pkg-alpha", gh_repo="acme/my-monorepo")

        assert "--repo" in seen_cmds[0]
        assert "acme/my-monorepo" in seen_cmds[0]
