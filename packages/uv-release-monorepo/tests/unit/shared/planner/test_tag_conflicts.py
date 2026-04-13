"""Tests for tag conflict checking via the resolution state machine.

These tests verify that resolve_release() correctly detects tag conflicts
and respects the skip set. They replace the old tests that called the
planner's private _find_tag_conflicts / _check_tag_conflicts methods.
"""

from __future__ import annotations

import pytest

from uv_release_monorepo.shared.resolution import (
    ReleaseConflictError,
    resolve_release,
)


PKG = "pkg-a"


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


class TestTagConflicts:
    """Tests for tag conflict detection in resolve_release()."""

    def test_no_conflicts_when_tags_missing(self) -> None:
        r = resolve_release("1.0.0.dev0", PKG, _repo())
        assert r.release_version == "1.0.0"

    def test_release_tag_conflict_detected(self) -> None:
        with pytest.raises(ReleaseConflictError, match="already released"):
            resolve_release("1.0.0.dev0", PKG, _repo(f"{PKG}/v1.0.0"))

    def test_release_tag_conflict_skipped_when_release_skipped(self) -> None:
        """Clean version + skip={uvr-release} allows existing release tag."""
        r = resolve_release(
            "1.0.0",
            PKG,
            _repo(f"{PKG}/v0.9.0", f"{PKG}/v1.0.0"),
            skip=frozenset({"uvr-release"}),
        )
        assert r.release_version == "1.0.0"

    def test_baseline_tag_conflict_always_checked(self) -> None:
        with pytest.raises(ReleaseConflictError, match="Tag"):
            resolve_release("1.0.0.dev0", PKG, _repo(f"{PKG}/v1.0.1.dev0-base"))

    def test_baseline_tag_conflict_even_with_release_skipped(self) -> None:
        with pytest.raises(ReleaseConflictError, match="Tag"):
            resolve_release(
                "1.0.0",
                PKG,
                _repo(f"{PKG}/v0.9.0", f"{PKG}/v1.0.1.dev0-base"),
                skip=frozenset({"uvr-release"}),
            )
