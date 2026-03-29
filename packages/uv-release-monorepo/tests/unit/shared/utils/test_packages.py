"""Tests for package discovery utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from uv_release_monorepo.shared.utils.packages import find_packages


class TestDiscoverPackagesRoot:
    """Tests for find_packages() root parameter."""

    @patch("uv_release_monorepo.shared.utils.packages.print_step")
    def test_accepts_explicit_root(self, mock_step: MagicMock, tmp_path: Path) -> None:
        """find_packages() uses the provided root directory."""
        root = tmp_path
        (root / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        )
        pkg_dir = root / "packages" / "my-pkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(
            '[project]\nname = "my-pkg"\nversion = "0.1.0"\n'
        )

        result = find_packages(root=root)

        assert "my-pkg" in result
        assert result["my-pkg"].version == "0.1.0"
