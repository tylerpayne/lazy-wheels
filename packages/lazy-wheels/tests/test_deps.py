"""Tests for lazy_wheels.deps."""

from __future__ import annotations

from pathlib import Path

from lazy_wheels.deps import dep_canonical_name, pin_dep, rewrite_pyproject


class TestDepCanonicalName:
    def test_simple_name(self) -> None:
        assert dep_canonical_name("requests") == "requests"

    def test_with_version_spec(self) -> None:
        assert dep_canonical_name("requests>=2.0") == "requests"

    def test_with_version_bound(self) -> None:
        assert dep_canonical_name("requests>=2.0,<3.0") == "requests"

    def test_with_extras(self) -> None:
        assert dep_canonical_name("requests[security]>=2.0") == "requests"

    def test_normalizes_underscores(self) -> None:
        assert dep_canonical_name("my_package>=1.0") == "my-package"

    def test_normalizes_case(self) -> None:
        assert dep_canonical_name("MyPackage>=1.0") == "mypackage"


class TestPinDep:
    def test_simple_dep(self) -> None:
        assert pin_dep("requests", "2.31.0") == "requests==2.31.0"

    def test_dep_with_existing_version(self) -> None:
        assert pin_dep("requests>=2.0", "2.31.0") == "requests==2.31.0"

    def test_dep_with_existing_version_bound(self) -> None:
        assert pin_dep("requests>=2.0,<3.0", "2.31.0") == "requests==2.31.0"

    def test_preserves_extras(self) -> None:
        assert (
            pin_dep("requests[security]>=2.0", "2.31.0") == "requests[security]==2.31.0"
        )

    def test_preserves_multiple_extras_sorted(self) -> None:
        result = pin_dep("pkg[z,a,m]>=1.0", "3.0.0")
        assert result == "pkg[a,m,z]==3.0.0"


class TestRewritePyproject:
    def test_updates_version(self, tmp_pyproject: Path) -> None:
        rewrite_pyproject(tmp_pyproject, "2.0.0", {})
        content = tmp_pyproject.read_text()
        assert 'version = "2.0.0"' in content

    def test_pins_internal_deps(self, tmp_pyproject: Path) -> None:
        rewrite_pyproject(tmp_pyproject, "2.0.0", {"internal-dep": "1.5.0"})
        content = tmp_pyproject.read_text()
        assert "internal-dep==1.5.0" in content

    def test_pins_optional_deps(self, tmp_pyproject: Path) -> None:
        rewrite_pyproject(tmp_pyproject, "2.0.0", {"another-internal": "0.8.0"})
        content = tmp_pyproject.read_text()
        assert "another-internal==0.8.0" in content

    def test_pins_dependency_groups(self, tmp_pyproject: Path) -> None:
        rewrite_pyproject(tmp_pyproject, "2.0.0", {"group-internal": "0.2.0"})
        content = tmp_pyproject.read_text()
        assert "group-internal==0.2.0" in content

    def test_preserves_external_deps(self, tmp_pyproject: Path) -> None:
        rewrite_pyproject(tmp_pyproject, "2.0.0", {"internal-dep": "1.5.0"})
        content = tmp_pyproject.read_text()
        assert 'requests>=2.0"' in content
