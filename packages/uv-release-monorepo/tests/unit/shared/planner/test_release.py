"""Release matrix: 27 versions × 2 modes = 54 cells.

Every valid PEP 440 version form × {default, --dev} → (release_version, next_version).
Expected outcomes are static literals — no version logic in the test.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pygit2
import pytest

from uv_release_monorepo.shared.context import RepositoryContext
from uv_release_monorepo.shared.models import PackageInfo, PlanConfig
from uv_release_monorepo.shared.planner import ReleasePlanner

E = "ERROR"


def _planner(release_type: str = "stable") -> ReleasePlanner:
    return ReleasePlanner(
        PlanConfig(
            rebuild_all=True,
            matrix={},
            uvr_version="0.7.1",
            ci_publish=False,
            dev_release=(release_type == "dev"),
            dry_run=True,
        ),
        RepositoryContext(
            repo=MagicMock(spec=pygit2.Repository),
            packages={},
        ),
    )


def _release_and_bump(planner: ReleasePlanner, version: str) -> tuple[str, str]:
    changed = {"alpha": PackageInfo(path="packages/alpha", version=version)}
    release_versions = planner._compute_release_versions(changed)
    versioned = {
        "alpha": PackageInfo(path="packages/alpha", version=release_versions["alpha"])
    }
    next_versions = planner._compute_next_versions(versioned)
    return release_versions["alpha"], next_versions["alpha"]


# ---------------------------------------------------------------------------
# Static expected outcomes: (version, release_type, release_version, next_version)
# ---------------------------------------------------------------------------

# fmt: off
_MATRIX: list[tuple[str, str, str, str]] = [
    # ── uvr release (no flags → "stable") ──
    # stable base
    ("1.0.1",              "stable", "1.0.1",       "1.0.2.dev0"),
    ("1.0.1.dev0",         "stable", "1.0.1",       "1.0.2.dev0"),
    ("1.0.1.dev3",         "stable", "1.0.1",       "1.0.2.dev0"),
    # alpha
    ("1.0.1a0",            "stable", "1.0.1a0",     "1.0.1a1.dev0"),
    ("1.0.1a0.dev0",       "stable", "1.0.1a0",     "1.0.1a1.dev0"),
    ("1.0.1a0.dev3",       "stable", "1.0.1a0",     "1.0.1a1.dev0"),
    ("1.0.1a2",            "stable", "1.0.1a2",     "1.0.1a3.dev0"),
    ("1.0.1a2.dev0",       "stable", "1.0.1a2",     "1.0.1a3.dev0"),
    ("1.0.1a2.dev3",       "stable", "1.0.1a2",     "1.0.1a3.dev0"),
    # beta
    ("1.0.1b0",            "stable", "1.0.1b0",     "1.0.1b1.dev0"),
    ("1.0.1b0.dev0",       "stable", "1.0.1b0",     "1.0.1b1.dev0"),
    ("1.0.1b0.dev3",       "stable", "1.0.1b0",     "1.0.1b1.dev0"),
    ("1.0.1b2",            "stable", "1.0.1b2",     "1.0.1b3.dev0"),
    ("1.0.1b2.dev0",       "stable", "1.0.1b2",     "1.0.1b3.dev0"),
    ("1.0.1b2.dev3",       "stable", "1.0.1b2",     "1.0.1b3.dev0"),
    # rc
    ("1.0.1rc0",           "stable", "1.0.1rc0",    "1.0.1rc1.dev0"),
    ("1.0.1rc0.dev0",      "stable", "1.0.1rc0",    "1.0.1rc1.dev0"),
    ("1.0.1rc0.dev3",      "stable", "1.0.1rc0",    "1.0.1rc1.dev0"),
    ("1.0.1rc2",           "stable", "1.0.1rc2",    "1.0.1rc3.dev0"),
    ("1.0.1rc2.dev0",      "stable", "1.0.1rc2",    "1.0.1rc3.dev0"),
    ("1.0.1rc2.dev3",      "stable", "1.0.1rc2",    "1.0.1rc3.dev0"),
    # post
    ("1.0.1.post0",        "stable", "1.0.1.post0", "1.0.1.post1.dev0"),
    ("1.0.1.post0.dev0",   "stable", "1.0.1.post0", "1.0.1.post1.dev0"),
    ("1.0.1.post0.dev3",   "stable", "1.0.1.post0", "1.0.1.post1.dev0"),
    ("1.0.1.post2",        "stable", "1.0.1.post2", "1.0.1.post3.dev0"),
    ("1.0.1.post2.dev0",   "stable", "1.0.1.post2", "1.0.1.post3.dev0"),
    ("1.0.1.post2.dev3",   "stable", "1.0.1.post2", "1.0.1.post3.dev0"),

    # ── uvr release --dev ──
    # stable base
    ("1.0.1",              "dev",   "1.0.1.dev0",       "1.0.1.dev1"),
    ("1.0.1.dev0",         "dev",   "1.0.1.dev0",       "1.0.1.dev1"),
    ("1.0.1.dev3",         "dev",   "1.0.1.dev3",       "1.0.1.dev4"),
    # alpha
    ("1.0.1a0",            "dev",   "1.0.1a0.dev0",     "1.0.1a0.dev1"),
    ("1.0.1a0.dev0",       "dev",   "1.0.1a0.dev0",     "1.0.1a0.dev1"),
    ("1.0.1a0.dev3",       "dev",   "1.0.1a0.dev3",     "1.0.1a0.dev4"),
    ("1.0.1a2",            "dev",   "1.0.1a2.dev0",     "1.0.1a2.dev1"),
    ("1.0.1a2.dev0",       "dev",   "1.0.1a2.dev0",     "1.0.1a2.dev1"),
    ("1.0.1a2.dev3",       "dev",   "1.0.1a2.dev3",     "1.0.1a2.dev4"),
    # beta
    ("1.0.1b0",            "dev",   "1.0.1b0.dev0",     "1.0.1b0.dev1"),
    ("1.0.1b0.dev0",       "dev",   "1.0.1b0.dev0",     "1.0.1b0.dev1"),
    ("1.0.1b0.dev3",       "dev",   "1.0.1b0.dev3",     "1.0.1b0.dev4"),
    ("1.0.1b2",            "dev",   "1.0.1b2.dev0",     "1.0.1b2.dev1"),
    ("1.0.1b2.dev0",       "dev",   "1.0.1b2.dev0",     "1.0.1b2.dev1"),
    ("1.0.1b2.dev3",       "dev",   "1.0.1b2.dev3",     "1.0.1b2.dev4"),
    # rc
    ("1.0.1rc0",           "dev",   "1.0.1rc0.dev0",    "1.0.1rc0.dev1"),
    ("1.0.1rc0.dev0",      "dev",   "1.0.1rc0.dev0",    "1.0.1rc0.dev1"),
    ("1.0.1rc0.dev3",      "dev",   "1.0.1rc0.dev3",    "1.0.1rc0.dev4"),
    ("1.0.1rc2",           "dev",   "1.0.1rc2.dev0",    "1.0.1rc2.dev1"),
    ("1.0.1rc2.dev0",      "dev",   "1.0.1rc2.dev0",    "1.0.1rc2.dev1"),
    ("1.0.1rc2.dev3",      "dev",   "1.0.1rc2.dev3",    "1.0.1rc2.dev4"),
    # post
    ("1.0.1.post0",        "dev",   "1.0.1.post0.dev0", "1.0.1.post0.dev1"),
    ("1.0.1.post0.dev0",   "dev",   "1.0.1.post0.dev0", "1.0.1.post0.dev1"),
    ("1.0.1.post0.dev3",   "dev",   "1.0.1.post0.dev3", "1.0.1.post0.dev4"),
    ("1.0.1.post2",        "dev",   "1.0.1.post2.dev0", "1.0.1.post2.dev1"),
    ("1.0.1.post2.dev0",   "dev",   "1.0.1.post2.dev0", "1.0.1.post2.dev1"),
    ("1.0.1.post2.dev3",   "dev",   "1.0.1.post2.dev3", "1.0.1.post2.dev4"),
]
# fmt: on

assert len(_MATRIX) == 54, f"Expected 54 cells, got {len(_MATRIX)}"


class TestReleaseMatrix:
    """27 versions × 2 release modes = 54 cells."""

    @pytest.mark.parametrize(
        "version,release_type,expected_release,expected_next",
        _MATRIX,
        ids=[f"{v}+{rt}" for v, rt, _, _ in _MATRIX],
    )
    def test_release(
        self,
        version: str,
        release_type: str,
        expected_release: str,
        expected_next: str,
    ) -> None:
        release, next_ver = _release_and_bump(_planner(release_type), version)
        assert release == expected_release
        assert next_ver == expected_next
