"""Tests for DownloadIntent: guard and construction."""

from __future__ import annotations

import pytest

from uv_release.intents.download import DownloadIntent
from uv_release.types import (
    Config,
    Publishing,
    Workspace,
)


def _workspace() -> Workspace:
    return Workspace(
        packages={},
        config=Config(uvr_version="0.1.0"),
        runners={},
        publishing=Publishing(),
    )


# ---------------------------------------------------------------------------
# DownloadIntent construction
# ---------------------------------------------------------------------------


class TestDownloadIntentConstruction:
    """DownloadIntent is a frozen Pydantic model with correct defaults."""

    def test_type_discriminator(self) -> None:
        intent = DownloadIntent()
        assert intent.type == "download"

    def test_defaults(self) -> None:
        intent = DownloadIntent()
        assert intent.package == ""
        assert intent.release_tag == ""
        assert intent.run_id == ""
        assert intent.repo == ""
        assert intent.output == "dist"

    def test_frozen(self) -> None:
        intent = DownloadIntent()
        with pytest.raises(Exception):
            intent.package = "something"


# ---------------------------------------------------------------------------
# DownloadIntent.guard
# ---------------------------------------------------------------------------


class TestDownloadGuard:
    """guard raises ValueError when no package and no run_id."""

    def test_no_package_no_run_id_raises(self) -> None:
        ws = _workspace()
        intent = DownloadIntent()
        with pytest.raises(ValueError, match="Specify a package name or --run-id"):
            intent.guard(ws)

    def test_with_package_passes(self) -> None:
        ws = _workspace()
        intent = DownloadIntent(package="my-pkg")
        intent.guard(ws)  # should not raise

    def test_with_run_id_passes(self) -> None:
        ws = _workspace()
        intent = DownloadIntent(run_id="12345")
        intent.guard(ws)  # should not raise

    def test_with_both_passes(self) -> None:
        ws = _workspace()
        intent = DownloadIntent(package="my-pkg", run_id="12345")
        intent.guard(ws)  # should not raise
