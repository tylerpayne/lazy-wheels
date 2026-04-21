"""Tests for InstallIntent: guard and construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from uv_release.intents.install import InstallIntent


# ---------------------------------------------------------------------------
# InstallIntent construction
# ---------------------------------------------------------------------------


class TestInstallIntentConstruction:
    """InstallIntent is a frozen Pydantic model with correct defaults."""

    def test_type_discriminator(self) -> None:
        intent = InstallIntent()
        assert intent.type == "install"

    def test_defaults(self) -> None:
        intent = InstallIntent()
        assert intent.packages == []
        assert intent.dist == ""
        assert intent.repo == ""

    def test_frozen(self) -> None:
        intent = InstallIntent()
        with pytest.raises(Exception):
            intent.dist = "something"


# ---------------------------------------------------------------------------
# InstallIntent.guard
# ---------------------------------------------------------------------------


class TestInstallGuard:
    """guard validates that we have something to install."""

    def test_no_packages_no_dist_raises(self) -> None:
        intent = InstallIntent()
        with pytest.raises(ValueError, match="Specify at least one package or --dist"):
            intent.guard()

    def test_dist_not_a_directory_raises(self, tmp_path: Path) -> None:
        nonexistent = str(tmp_path / "no-such-dir")
        intent = InstallIntent(dist=nonexistent)
        with pytest.raises(ValueError, match="Directory not found"):
            intent.guard()

    def test_with_packages_passes(self) -> None:
        intent = InstallIntent(packages=["my-pkg"])
        intent.guard()  # should not raise

    def test_with_dist_dir_passes(self, tmp_path: Path) -> None:
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        intent = InstallIntent(dist=str(dist_dir))
        intent.guard()  # should not raise
