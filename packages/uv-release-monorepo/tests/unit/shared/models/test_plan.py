"""Tests for uv_release_monorepo.models."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from uv_release_monorepo.shared.models import (
    BuildStage,
    ChangedPackage,
    FetchGithubReleaseCommand,
    FetchRunArtifactsCommand,
    PackageInfo,
    ReleasePlan,
    ShellCommand,
    _validate_runner_key,
)

_SUBPROCESS_RUN = "uv_release_monorepo.shared.models.plan.subprocess.run"


class TestValidateRunnerKey:
    """Tests for _validate_runner_key parsing."""

    def test_compact_json_string(self) -> None:
        assert _validate_runner_key('["ubuntu-latest"]') == ("ubuntu-latest",)

    def test_multiline_json_string(self) -> None:
        """Multiline JSON from GitHub Actions toJSON() is normalized before parsing."""
        multiline = '[\n  "self-hosted",\n  "windows",\n  "arm64"\n]'
        assert _validate_runner_key(multiline) == ("self-hosted", "windows", "arm64")

    def test_list_input(self) -> None:
        assert _validate_runner_key(["ubuntu-latest"]) == ("ubuntu-latest",)

    def test_tuple_input(self) -> None:
        assert _validate_runner_key(("macos-14",)) == ("macos-14",)

    def test_bare_words_from_powershell(self) -> None:
        """PowerShell strips double-quotes, leaving bare words."""
        bare = "[ self-hosted, windows, arm64 ]"
        assert _validate_runner_key(bare) == ("self-hosted", "windows", "arm64")

    def test_multiline_bare_words(self) -> None:
        """Multiline AND stripped quotes (both mangling forms combined)."""
        mangled = "[\n  self-hosted,\n  windows,\n  arm64\n]"
        assert _validate_runner_key(mangled) == ("self-hosted", "windows", "arm64")


class TestPackageInfo:
    def test_create_with_required_fields(self) -> None:
        pkg = PackageInfo(path="packages/foo", version="1.0.0")
        assert pkg.path == "packages/foo"
        assert pkg.version == "1.0.0"
        assert pkg.deps == []

    def test_create_with_deps(self) -> None:
        pkg = PackageInfo(path="libs/bar", version="2.1.0", deps=["foo", "baz"])
        assert pkg.deps == ["foo", "baz"]

    def test_deps_is_mutable(self) -> None:
        pkg = PackageInfo(path="pkg", version="1.0.0")
        pkg.deps.append("new-dep")
        assert pkg.deps == ["new-dep"]


class TestReleasePlan:
    def _make_plan(self) -> ReleasePlan:
        alpha = ChangedPackage(
            path="packages/alpha",
            version="0.1.5",
            deps=[],
            current_version="0.1.5.dev0",
            release_version="0.1.5",
            next_version="0.1.6.dev0",
            runners=[["ubuntu-latest"]],
        )
        beta = PackageInfo(path="packages/beta", version="0.2.0", deps=["pkg-alpha"])
        return ReleasePlan(
            uvr_version="0.3.0",
            rebuild_all=False,
            changed={"pkg-alpha": alpha},
            unchanged={"pkg-beta": beta},
        )

    def test_schema_version_defaults_to_12(self) -> None:
        plan = self._make_plan()
        assert plan.schema_version == 12

    def test_extra_keys_survive_round_trip(self) -> None:
        plan = self._make_plan()
        data = plan.model_dump()
        data["deploy_env"] = "staging"
        data["custom_flags"] = {"notify": True}

        restored = ReleasePlan.model_validate(data)
        assert restored.model_extra is not None
        assert restored.model_extra["deploy_env"] == "staging"

        # JSON round-trip
        json_str = restored.model_dump_json()
        final = ReleasePlan.model_validate_json(json_str)
        assert final.model_extra is not None
        assert final.model_extra["deploy_env"] == "staging"
        assert final.model_extra["custom_flags"] == {"notify": True}

    def test_round_trip_json(self) -> None:
        plan = self._make_plan()
        restored = ReleasePlan.model_validate_json(plan.model_dump_json())
        assert restored.uvr_version == plan.uvr_version
        assert restored.changed["pkg-alpha"].version == "0.1.5"
        assert restored.unchanged["pkg-beta"].version == "0.2.0"

    def test_build_matrix_shape(self) -> None:
        """build_matrix serializes as list of runner label sets."""
        plan = self._make_plan()
        data = plan.model_dump()
        assert data["build_matrix"] == [["ubuntu-latest"]]


class TestShellCommand:
    """Tests for ShellCommand.execute()."""

    @patch(_SUBPROCESS_RUN)
    def test_execute_calls_subprocess(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        cmd = ShellCommand(args=["echo", "hello"])
        result = cmd.execute()
        mock_run.assert_called_once_with(["echo", "hello"])
        assert result.returncode == 0

    def test_type_discriminator(self) -> None:
        cmd = ShellCommand(args=["echo"])
        assert cmd.type == "shell"


class TestFetchGithubReleaseCommand:
    """Tests for FetchGithubReleaseCommand.execute()."""

    def _mock_gh_view(self, asset_names: list[str]) -> MagicMock:
        """Return a MagicMock for the gh release view subprocess result."""
        assets = [{"name": n} for n in asset_names]
        result = MagicMock(returncode=0, stdout=json.dumps({"assets": assets}))
        return result

    @patch(_SUBPROCESS_RUN)
    def test_prefers_universal_wheel(self, mock_run: MagicMock) -> None:
        """When a py3-none-any wheel exists, only that is downloaded."""
        view_result = self._mock_gh_view(
            [
                "pkg_alpha-1.0.0-py3-none-any.whl",
                "pkg_alpha-1.0.0-cp311-cp311-linux_x86_64.whl",
            ]
        )
        download_result = MagicMock(returncode=0)
        mock_run.side_effect = [view_result, download_result]

        cmd = FetchGithubReleaseCommand(
            tag="pkg-alpha/v1.0.0",
            dist_name="pkg_alpha",
            directory="deps",
        )
        result = cmd.execute()

        assert result.returncode == 0
        download_call = mock_run.call_args_list[1]
        download_args = (
            download_call.args[0] if download_call.args else download_call[0][0]
        )
        assert "--pattern" in download_args
        pattern_idx = download_args.index("--pattern")
        assert download_args[pattern_idx + 1] == "pkg_alpha-1.0.0-py3-none-any.whl"
        # Only one pattern — the universal wheel
        assert download_args.count("--pattern") == 1

    @patch(_SUBPROCESS_RUN)
    def test_filters_platform_wheels(self, mock_run: MagicMock) -> None:
        """When no universal wheel exists, filters by platform compatibility."""
        import platform as _platform

        # Use py3-none-<platform> so the test doesn't depend on cpython version.
        # One wheel matches the test host, the other doesn't.
        if _platform.system() == "Darwin":
            compatible = "pkg_alpha-1.0.0-py3-none-macosx_11_0_arm64.whl"
            incompatible = "pkg_alpha-1.0.0-py3-none-linux_x86_64.whl"
        else:
            compatible = "pkg_alpha-1.0.0-py3-none-linux_x86_64.whl"
            incompatible = "pkg_alpha-1.0.0-py3-none-macosx_11_0_arm64.whl"

        view_result = self._mock_gh_view([incompatible, compatible])
        download_result = MagicMock(returncode=0)
        mock_run.side_effect = [view_result, download_result]

        cmd = FetchGithubReleaseCommand(
            tag="pkg-alpha/v1.0.0",
            dist_name="pkg_alpha",
        )
        result = cmd.execute()

        assert result.returncode == 0
        download_call = mock_run.call_args_list[1]
        download_args = (
            download_call.args[0] if download_call.args else download_call[0][0]
        )
        patterns = [
            download_args[i + 1]
            for i, a in enumerate(download_args)
            if a == "--pattern"
        ]
        assert len(patterns) == 1
        assert patterns[0] == compatible

    @patch(_SUBPROCESS_RUN)
    def test_returns_failure_when_no_compatible_wheels(
        self, mock_run: MagicMock
    ) -> None:
        """Returns non-zero when no wheels match the current platform."""
        # Use a fake platform tag that won't match any real system
        view_result = self._mock_gh_view(
            [
                "pkg_alpha-1.0.0-cp311-cp311-fakeos_99_0_fakearch.whl",
            ]
        )
        mock_run.return_value = view_result

        cmd = FetchGithubReleaseCommand(
            tag="pkg-alpha/v1.0.0",
            dist_name="pkg_alpha",
        )
        result = cmd.execute()

        assert result.returncode != 0

    @patch(_SUBPROCESS_RUN)
    def test_returns_failure_when_no_assets(self, mock_run: MagicMock) -> None:
        """Returns non-zero when the release has no matching wheel assets."""
        view_result = self._mock_gh_view(["README.md", "checksums.txt"])
        mock_run.return_value = view_result

        cmd = FetchGithubReleaseCommand(
            tag="pkg-alpha/v1.0.0",
            dist_name="pkg_alpha",
        )
        result = cmd.execute()

        assert result.returncode != 0

    @patch(_SUBPROCESS_RUN)
    def test_returns_failure_when_gh_view_fails(self, mock_run: MagicMock) -> None:
        """Returns non-zero when gh release view fails."""
        mock_run.return_value = MagicMock(returncode=1)

        cmd = FetchGithubReleaseCommand(
            tag="pkg-alpha/v1.0.0",
            dist_name="pkg_alpha",
        )
        result = cmd.execute()

        assert result.returncode != 0

    def test_type_discriminator(self) -> None:
        cmd = FetchGithubReleaseCommand(
            tag="pkg-alpha/v1.0.0",
            dist_name="pkg_alpha",
        )
        assert cmd.type == "fetch_release"

    def test_serialization_round_trip(self) -> None:
        """FetchGithubReleaseCommand survives JSON serialization in a BuildStage."""
        stage = BuildStage(
            setup=[
                ShellCommand(args=["mkdir", "-p", "deps"]),
                FetchGithubReleaseCommand(
                    tag="pkg-alpha/v1.0.0",
                    dist_name="pkg_alpha",
                    directory="deps",
                    label="Fetch pkg-alpha",
                ),
            ],
        )
        data = stage.model_dump(mode="json")
        restored = BuildStage.model_validate(data)
        assert len(restored.setup) == 2
        assert isinstance(restored.setup[0], ShellCommand)
        assert isinstance(restored.setup[1], FetchGithubReleaseCommand)
        assert restored.setup[1].tag == "pkg-alpha/v1.0.0"

    def test_backwards_compat_missing_type(self) -> None:
        """Old plan JSON without type field deserializes as ShellCommand."""
        data = {
            "setup": [{"args": ["mkdir", "-p", "deps"]}],
            "packages": {},
            "cleanup": [],
        }
        stage = BuildStage.model_validate(data)
        assert isinstance(stage.setup[0], ShellCommand)
        assert stage.setup[0].args == ["mkdir", "-p", "deps"]


class TestFetchRunArtifactsCommand:
    """Tests for FetchRunArtifactsCommand.execute()."""

    @patch(_SUBPROCESS_RUN)
    def test_prefers_universal_wheel(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """When a py3-none-any wheel exists, only that is copied."""
        out = tmp_path / "out"

        def fake_run(cmd, **kwargs):
            cmd = list(cmd)
            result = MagicMock(returncode=0)
            if "download" in cmd:
                dir_idx = cmd.index("--dir") + 1
                base = Path(cmd[dir_idx])
                subdir = base / "wheels-ubuntu-latest"
                subdir.mkdir(parents=True, exist_ok=True)
                (subdir / "pkg_alpha-1.0.0-py3-none-any.whl").write_bytes(b"")
                subdir2 = base / "wheels-macos-14"
                subdir2.mkdir(parents=True, exist_ok=True)
                (
                    subdir2 / "pkg_alpha-1.0.0-py3-none-macosx_11_0_arm64.whl"
                ).write_bytes(b"")
            return result

        mock_run.side_effect = fake_run

        cmd = FetchRunArtifactsCommand(
            run_id="12345",
            dist_name="pkg_alpha",
            directory=str(out),
        )
        result = cmd.execute()

        assert result.returncode == 0
        wheels = list(out.glob("*.whl"))
        assert len(wheels) == 1
        assert wheels[0].name == "pkg_alpha-1.0.0-py3-none-any.whl"

    @patch(_SUBPROCESS_RUN)
    def test_returns_failure_when_no_wheels(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Returns non-zero when the run has no matching wheels."""
        out = tmp_path / "out"

        def fake_run(cmd, **kwargs):
            cmd = list(cmd)
            result = MagicMock(returncode=0)
            if "download" in cmd:
                dir_idx = cmd.index("--dir") + 1
                base = Path(cmd[dir_idx])
                subdir = base / "wheels-ubuntu-latest"
                subdir.mkdir(parents=True, exist_ok=True)
                # No matching wheels
                (subdir / "other_pkg-1.0.0-py3-none-any.whl").write_bytes(b"")
            return result

        mock_run.side_effect = fake_run

        cmd = FetchRunArtifactsCommand(
            run_id="12345",
            dist_name="pkg_alpha",
            directory=str(out),
        )
        result = cmd.execute()

        assert result.returncode != 0

    @patch(_SUBPROCESS_RUN)
    def test_returns_failure_when_download_fails(self, mock_run: MagicMock) -> None:
        """Returns non-zero when gh run download fails."""
        mock_run.return_value = MagicMock(returncode=1)

        cmd = FetchRunArtifactsCommand(
            run_id="12345",
            dist_name="pkg_alpha",
        )
        result = cmd.execute()

        assert result.returncode != 0

    def test_type_discriminator(self) -> None:
        cmd = FetchRunArtifactsCommand(run_id="12345", dist_name="pkg_alpha")
        assert cmd.type == "fetch_run_artifacts"
