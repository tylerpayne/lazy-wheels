"""Tests for detect_changes using a mock GitRepo."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from uv_release.detect.detector import detect_changes
from uv_release.git import GitRepo
from uv_release.types import (
    Config,
    Package,
    PlanParams,
    Publishing,
    Version,
    Workspace,
)


def _workspace(*packages: Package) -> Workspace:
    pkgs = {p.name: p for p in packages}
    return Workspace(
        packages=pkgs,
        config=Config(uvr_version="0.1.0"),
        runners={},
        publishing=Publishing(),
    )


def _pkg(
    name: str, version: str = "1.0.0.dev0", deps: list[str] | None = None
) -> Package:
    return Package(
        name=name,
        path=f"packages/{name}",
        version=Version.parse(version),
        deps=deps or [],
    )


def _default_params(**overrides: object) -> PlanParams:
    return PlanParams(**overrides)  # type: ignore[arg-type]


def _dev_params(**overrides: object) -> PlanParams:
    return PlanParams(dev_release=True, **overrides)  # type: ignore[arg-type]


def _mock_repo(
    tags: dict[str, str] | None = None,
    changed_paths: set[str] | None = None,
    log_output: str = "abc Fix something",
) -> MagicMock:
    """Build a mock GitRepo."""
    tags = tags or {}
    changed_paths = changed_paths or set()

    repo = MagicMock(spec=GitRepo)
    repo.find_tag.side_effect = lambda name: tags.get(name)
    repo.list_tags.side_effect = lambda prefix: [
        n for n in tags if n.startswith(prefix)
    ]
    repo.head_commit.return_value = "head000"
    repo.path_changed.side_effect = lambda from_c, to_c, path: path in changed_paths
    repo.commit_log.return_value = log_output
    repo.diff_stats.return_value = "+10 / -5"
    return repo


class TestDetectChanges:
    def test_changed_files_produces_change(self) -> None:
        pkg = _pkg("alpha")
        ws = _workspace(pkg)
        repo = _mock_repo(
            tags={"alpha/v1.0.0.dev0-base": "commit_a"},
            changed_paths={"packages/alpha"},
        )
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(ws, _dev_params())
        assert {c.package.name for c in changes} == {"alpha"}

    def test_unchanged_files_not_in_output(self) -> None:
        pkg = _pkg("alpha")
        ws = _workspace(pkg)
        repo = _mock_repo(
            tags={"alpha/v1.0.0.dev0-base": "commit_a"},
            changed_paths=set(),
        )
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(ws, _dev_params())
        assert len(changes) == 0

    def test_no_baseline_means_first_release(self) -> None:
        pkg = _pkg("alpha")
        ws = _workspace(pkg)
        repo = _mock_repo(tags={})
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(ws, _dev_params())
        assert {c.package.name for c in changes} == {"alpha"}
        assert changes[0].baseline is None

    def test_rebuild_all_forces_all_changed(self) -> None:
        alpha = _pkg("alpha")
        beta = _pkg("beta")
        ws = _workspace(alpha, beta)
        repo = _mock_repo(
            tags={"alpha/v1.0.0.dev0-base": "ca", "beta/v1.0.0.dev0-base": "cb"},
            changed_paths=set(),
        )
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(ws, _dev_params(rebuild_all=True))
        assert {c.package.name for c in changes} == {"alpha", "beta"}

    def test_rebuild_forces_specific_package(self) -> None:
        alpha = _pkg("alpha")
        beta = _pkg("beta")
        ws = _workspace(alpha, beta)
        repo = _mock_repo(
            tags={"alpha/v1.0.0.dev0-base": "ca", "beta/v1.0.0.dev0-base": "cb"},
            changed_paths=set(),
        )
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(ws, _dev_params(rebuild=frozenset({"alpha"})))
        assert {c.package.name for c in changes} == {"alpha"}

    def test_restrict_packages_filters_output(self) -> None:
        alpha = _pkg("alpha")
        beta = _pkg("beta", deps=["alpha"])
        ws = _workspace(alpha, beta)
        repo = _mock_repo(tags={})
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(
                ws, _dev_params(restrict_packages=frozenset({"beta"}))
            )
        names = {c.package.name for c in changes}
        assert "beta" in names
        assert "alpha" in names

    def test_change_has_correct_baseline_tag(self) -> None:
        pkg = _pkg("alpha")
        ws = _workspace(pkg)
        repo = _mock_repo(
            tags={"alpha/v1.0.0.dev0-base": "commit_xyz"},
            changed_paths={"packages/alpha"},
        )
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(ws, _dev_params())
        assert changes[0].baseline is not None
        assert changes[0].baseline.commit == "commit_xyz"

    def test_change_has_commit_log_populated(self) -> None:
        pkg = _pkg("alpha")
        ws = _workspace(pkg)
        repo = _mock_repo(
            tags={"alpha/v1.0.0.dev0-base": "commit_a"},
            changed_paths={"packages/alpha"},
            log_output="abc123 Fix the bug",
        )
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(ws, _dev_params())
        assert changes[0].commit_log == "abc123 Fix the bug"

    def test_propagation_includes_transitive_dependents(self) -> None:
        alpha = _pkg("alpha")
        beta = _pkg("beta", deps=["alpha"])
        ws = _workspace(alpha, beta)
        repo = _mock_repo(
            tags={"alpha/v1.0.0.dev0-base": "ca", "beta/v1.0.0.dev0-base": "cb"},
            changed_paths={"packages/alpha"},
        )
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(ws, _dev_params())
        names = {c.package.name for c in changes}
        assert "alpha" in names
        assert "beta" in names


class TestDetectNoLongerChecksVersions:
    """detect_changes no longer raises for dev versions. Version checking moved to planner."""

    def test_dev_packages_with_default_params_returns_changes(self) -> None:
        """Changed dev packages with dev_release=False still return changes (no exception)."""
        pkg = _pkg("alpha", version="1.0.0.dev0")
        ws = _workspace(pkg)
        repo = _mock_repo(
            tags={"alpha/v1.0.0.dev0-base": "ca"},
            changed_paths={"packages/alpha"},
        )
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(ws, _default_params())
        assert len(changes) == 1
        assert changes[0].package.name == "alpha"

    def test_clean_versions_return_changes(self) -> None:
        """Changed packages with non-dev versions return changes."""
        pkg = _pkg("alpha", version="1.0.0")
        ws = _workspace(pkg)
        repo = _mock_repo(
            tags={"alpha/v0.9.0": "ca"},
            changed_paths={"packages/alpha"},
        )
        with patch("uv_release.detect.detector.GitRepo", return_value=repo):
            changes = detect_changes(ws, _default_params())
        assert len(changes) == 1
