"""Baseline resolution and release type validity tests.

Validates that for each (current_version, release_type) combination:
1. Invalid combinations are rejected
2. Valid combinations resolve to the correct baseline tag for change detection
3. Release version and bump version are correct

See the full matrix in the module-level docstring of resolve_baseline().
"""

from __future__ import annotations

import pytest

# resolve_baseline is the function under test.
# Signature: resolve_baseline(current_version, release_type, name, repo)
#   → returns baseline tag string, or raises ValueError for invalid combos.
from uv_release_monorepo.shared.utils.versions import resolve_baseline


PKG = "my-pkg"


class _FakeRepo:
    """Minimal repo mock that responds to reference lookups."""

    def __init__(self, tags: set[str]) -> None:
        self._tags = tags
        self.references = self
        self._refs = [f"refs/tags/{t}" for t in tags]

    def get(self, ref: str) -> object | None:
        return object() if ref in {f"refs/tags/{t}" for t in self._tags} else None

    def listall_references(self) -> list[str]:
        return self._refs


def _repo(*tags: str) -> _FakeRepo:
    return _FakeRepo(set(tags))


# ===================================================================
# Clean final: X.X.X
# ===================================================================


class TestCleanFinal:
    """Current version is a clean final (e.g. 1.0.1).

    User set version manually. All types valid with conflict check.
    Baseline is always find_previous_release(X.X.X).
    """

    @pytest.fixture
    def repo(self) -> _FakeRepo:
        return _repo(f"{PKG}/v1.0.0")

    def test_final(self, repo: _FakeRepo) -> None:
        result = resolve_baseline("1.0.1", "final", PKG, repo)
        assert result == f"{PKG}/v1.0.0"

    def test_pre(self, repo: _FakeRepo) -> None:
        result = resolve_baseline("1.0.1", "pre", PKG, repo)
        assert result == f"{PKG}/v1.0.0"

    def test_dev(self, repo: _FakeRepo) -> None:
        result = resolve_baseline("1.0.1", "dev", PKG, repo)
        assert result == f"{PKG}/v1.0.0"

    def test_post(self, repo: _FakeRepo) -> None:
        result = resolve_baseline("1.0.1", "post", PKG, repo)
        assert result == f"{PKG}/v1.0.0"


# ===================================================================
# Dev after final: X.X.X.dev0
# ===================================================================


class TestDevAfterFinal:
    """Current version is dev0 after a final (e.g. 1.0.1.dev0).

    Normal dev cycle. Most types use current baseline.
    Post is invalid — can't post-release something unreleased.
    Pre is invalid — no pre-release suffix in version.
    """

    def test_final(self) -> None:
        result = resolve_baseline("1.0.1.dev0", "final", PKG, _repo())
        assert result == f"{PKG}/v1.0.1.dev0-base"

    def test_pre_invalid(self) -> None:
        with pytest.raises(ValueError, match="pre"):
            resolve_baseline("1.0.1.dev0", "pre", PKG, _repo())

    def test_dev(self) -> None:
        result = resolve_baseline("1.0.1.dev0", "dev", PKG, _repo())
        assert result == f"{PKG}/v1.0.1.dev0-base"

    def test_post_invalid(self) -> None:
        with pytest.raises(ValueError, match="post"):
            resolve_baseline("1.0.1.dev0", "post", PKG, _repo())


# ===================================================================
# Dev N after final: X.X.X.devN (N > 0)
# ===================================================================


class TestDevNAfterFinal:
    """Current version is devN (N > 0) after a final (e.g. 1.0.1.dev3).

    Non-dev releases use dev0 baseline (start of cycle).
    Dev uses its own devN baseline.
    Pre is invalid — no pre-release suffix in version.
    """

    def test_final(self) -> None:
        result = resolve_baseline("1.0.1.dev3", "final", PKG, _repo())
        assert result == f"{PKG}/v1.0.1.dev0-base"

    def test_pre_invalid(self) -> None:
        with pytest.raises(ValueError, match="pre"):
            resolve_baseline("1.0.1.dev3", "pre", PKG, _repo())

    def test_dev(self) -> None:
        result = resolve_baseline("1.0.1.dev3", "dev", PKG, _repo())
        assert result == f"{PKG}/v1.0.1.dev3-base"

    def test_post_invalid(self) -> None:
        with pytest.raises(ValueError, match="post"):
            resolve_baseline("1.0.1.dev3", "post", PKG, _repo())


# ===================================================================
# Clean pre-release: X.X.X{k}N
# ===================================================================


class TestCleanPreRelease:
    """Current version is a clean pre-release (e.g. 1.0.1a3, 1.0.1b1, 1.0.1rc2).

    User set version manually. All types valid with conflict check.
    Baseline is always find_previous_release(X.X.X) — start of pre-release cycle.
    """

    @pytest.fixture
    def repo(self) -> _FakeRepo:
        return _repo(f"{PKG}/v1.0.0")

    @pytest.mark.parametrize("version", ["1.0.1a3", "1.0.1b1", "1.0.1rc2"])
    def test_final(self, version: str, repo: _FakeRepo) -> None:
        result = resolve_baseline(version, "final", PKG, repo)
        assert result == f"{PKG}/v1.0.0"

    @pytest.mark.parametrize("version", ["1.0.1a3", "1.0.1b1", "1.0.1rc2"])
    def test_pre(self, version: str, repo: _FakeRepo) -> None:
        result = resolve_baseline(version, "pre", PKG, repo)
        assert result == f"{PKG}/v1.0.0"

    @pytest.mark.parametrize("version", ["1.0.1a3", "1.0.1b1", "1.0.1rc2"])
    def test_dev(self, version: str, repo: _FakeRepo) -> None:
        result = resolve_baseline(version, "dev", PKG, repo)
        assert result == f"{PKG}/v1.0.0"

    @pytest.mark.parametrize("version", ["1.0.1a3", "1.0.1b1", "1.0.1rc2"])
    def test_post(self, version: str, repo: _FakeRepo) -> None:
        result = resolve_baseline(version, "post", PKG, repo)
        assert result == f"{PKG}/v1.0.0"


# ===================================================================
# Dev after pre-release: X.X.X{k}N.dev0
# ===================================================================


class TestDevAfterPreRelease:
    """Current version is dev0 after a pre-release (e.g. 1.0.1a3.dev0).

    Pre-release uses incremental baseline (kind is already in the version).
    Final uses cumulative baseline since last final.
    Post is invalid.
    """

    @pytest.fixture
    def repo(self) -> _FakeRepo:
        return _repo(f"{PKG}/v1.0.0")

    @pytest.mark.parametrize(
        "version", ["1.0.1a3.dev0", "1.0.1b1.dev0", "1.0.1rc2.dev0"]
    )
    def test_final_cumulative(self, version: str, repo: _FakeRepo) -> None:
        """Final from pre-release → cumulative since last final."""
        result = resolve_baseline(version, "final", PKG, repo)
        assert result == f"{PKG}/v1.0.0"

    @pytest.mark.parametrize(
        "version", ["1.0.1a3.dev0", "1.0.1b1.dev0", "1.0.1rc2.dev0"]
    )
    def test_pre_incremental(self, version: str) -> None:
        """Pre-release → incremental from current baseline."""
        result = resolve_baseline(version, "pre", PKG, _repo())
        assert result == f"{PKG}/v{version}-base"

    @pytest.mark.parametrize(
        "version", ["1.0.1a3.dev0", "1.0.1b1.dev0", "1.0.1rc2.dev0"]
    )
    def test_dev(self, version: str) -> None:
        result = resolve_baseline(version, "dev", PKG, _repo())
        assert result == f"{PKG}/v{version}-base"

    @pytest.mark.parametrize(
        "version", ["1.0.1a3.dev0", "1.0.1b1.dev0", "1.0.1rc2.dev0"]
    )
    def test_post_invalid(self, version: str) -> None:
        with pytest.raises(ValueError, match="post"):
            resolve_baseline(version, "post", PKG, _repo())


# ===================================================================
# Dev M after pre-release: X.X.X{k}N.devM (M > 0)
# ===================================================================


class TestDevMAfterPreRelease:
    """Current version is devM (M > 0) after a pre-release (e.g. 1.0.1a3.dev2).

    Pre-release uses dev0 baseline (start of dev cycle).
    Final uses cumulative baseline since last final.
    Dev uses devM baseline (not dev0).
    """

    @pytest.fixture
    def repo(self) -> _FakeRepo:
        return _repo(f"{PKG}/v1.0.0")

    @pytest.mark.parametrize(
        "version", ["1.0.1a3.dev2", "1.0.1b1.dev5", "1.0.1rc2.dev1"]
    )
    def test_final_cumulative(self, version: str, repo: _FakeRepo) -> None:
        result = resolve_baseline(version, "final", PKG, repo)
        assert result == f"{PKG}/v1.0.0"

    @pytest.mark.parametrize(
        "version", ["1.0.1a3.dev2", "1.0.1b1.dev5", "1.0.1rc2.dev1"]
    )
    def test_pre_incremental(self, version: str) -> None:
        """Pre-release uses dev0 baseline (start of dev cycle, not devM)."""
        result = resolve_baseline(version, "pre", PKG, _repo())
        assert result == f"{PKG}/v{version.rsplit('.dev', 1)[0]}.dev0-base"

    @pytest.mark.parametrize(
        "version", ["1.0.1a3.dev2", "1.0.1b1.dev5", "1.0.1rc2.dev1"]
    )
    def test_dev(self, version: str) -> None:
        result = resolve_baseline(version, "dev", PKG, _repo())
        assert result == f"{PKG}/v{version}-base"

    @pytest.mark.parametrize(
        "version", ["1.0.1a3.dev2", "1.0.1b1.dev5", "1.0.1rc2.dev1"]
    )
    def test_post_invalid(self, version: str) -> None:
        with pytest.raises(ValueError, match="post"):
            resolve_baseline(version, "post", PKG, _repo())


# ===================================================================
# Clean post-release: X.X.X.postN
# ===================================================================


class TestCleanPostRelease:
    """Current version is a clean post-release (e.g. 1.0.1.post2).

    User set version manually. All types valid with conflict check.
    Baseline is find_previous_release(X.X.X.postN).
    """

    @pytest.fixture
    def repo(self) -> _FakeRepo:
        return _repo(f"{PKG}/v1.0.1.post1", f"{PKG}/v1.0.1")

    def test_final(self, repo: _FakeRepo) -> None:
        result = resolve_baseline("1.0.1.post2", "final", PKG, repo)
        assert result == f"{PKG}/v1.0.1.post1"

    def test_pre(self, repo: _FakeRepo) -> None:
        result = resolve_baseline("1.0.1.post2", "pre", PKG, repo)
        assert result == f"{PKG}/v1.0.1.post1"

    def test_dev(self, repo: _FakeRepo) -> None:
        result = resolve_baseline("1.0.1.post2", "dev", PKG, repo)
        assert result == f"{PKG}/v1.0.1.post1"

    def test_post(self, repo: _FakeRepo) -> None:
        result = resolve_baseline("1.0.1.post2", "post", PKG, repo)
        assert result == f"{PKG}/v1.0.1.post1"


# ===================================================================
# Dev after post-release: X.X.X.postN.dev0
# ===================================================================


class TestDevAfterPostRelease:
    """Current version is dev0 after a post-release (e.g. 1.0.1.post2.dev0).

    Only post and dev are valid. Final and pre are invalid.
    """

    def test_post(self) -> None:
        result = resolve_baseline("1.0.1.post2.dev0", "post", PKG, _repo())
        assert result == f"{PKG}/v1.0.1.post2.dev0-base"

    def test_dev(self) -> None:
        result = resolve_baseline("1.0.1.post2.dev0", "dev", PKG, _repo())
        assert result == f"{PKG}/v1.0.1.post2.dev0-base"

    def test_final_invalid(self) -> None:
        with pytest.raises(ValueError, match="final"):
            resolve_baseline("1.0.1.post2.dev0", "final", PKG, _repo())

    def test_pre_invalid(self) -> None:
        with pytest.raises(ValueError, match="pre"):
            resolve_baseline("1.0.1.post2.dev0", "pre", PKG, _repo())


# ===================================================================
# Dev M after post-release: X.X.X.postN.devM (M > 0)
# ===================================================================


class TestDevMAfterPostRelease:
    """Current version is devM (M > 0) after a post-release (e.g. 1.0.1.post2.dev3).

    Post uses dev0 baseline. Dev uses devM baseline. Final/pre invalid.
    """

    def test_post(self) -> None:
        result = resolve_baseline("1.0.1.post2.dev3", "post", PKG, _repo())
        assert result == f"{PKG}/v1.0.1.post2.dev0-base"

    def test_dev(self) -> None:
        result = resolve_baseline("1.0.1.post2.dev3", "dev", PKG, _repo())
        assert result == f"{PKG}/v1.0.1.post2.dev3-base"

    def test_final_invalid(self) -> None:
        with pytest.raises(ValueError, match="final"):
            resolve_baseline("1.0.1.post2.dev3", "final", PKG, _repo())

    def test_pre_invalid(self) -> None:
        with pytest.raises(ValueError, match="pre"):
            resolve_baseline("1.0.1.post2.dev3", "pre", PKG, _repo())
