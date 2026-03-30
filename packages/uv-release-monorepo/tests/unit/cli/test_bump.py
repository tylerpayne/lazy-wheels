"""Bump matrix: 27 versions × 8 bump types = 216 cells.

Every valid PEP 440 version form × every bump type → expected result or error.
Expected outcomes are static literals — no version logic in the test.
"""

from __future__ import annotations

import pytest

from uv_release_monorepo.cli.bump import compute_bumped_version
from uv_release_monorepo.shared.utils.versions import validate_bump

# Map CLI bump names to PEP 440 short pre-release kinds (for validate_bump)
_PRE_KIND_MAP = {"alpha": "a", "beta": "b", "rc": "rc"}

# ---------------------------------------------------------------------------
# Static expected outcomes: (version, bump_type) → expected string or "ERROR"
# ---------------------------------------------------------------------------

E = "ERROR"

# fmt: off
_MATRIX: list[tuple[str, str, str]] = [
    # ── --major (27 cells, all → 2.0.0.dev0) ──
    ("1.0.1",              "major", "2.0.0.dev0"),
    ("1.0.1.dev0",         "major", "2.0.0.dev0"),
    ("1.0.1.dev3",         "major", "2.0.0.dev0"),
    ("1.0.1a0",            "major", "2.0.0.dev0"),
    ("1.0.1a0.dev0",       "major", "2.0.0.dev0"),
    ("1.0.1a0.dev3",       "major", "2.0.0.dev0"),
    ("1.0.1a2",            "major", "2.0.0.dev0"),
    ("1.0.1a2.dev0",       "major", "2.0.0.dev0"),
    ("1.0.1a2.dev3",       "major", "2.0.0.dev0"),
    ("1.0.1b0",            "major", "2.0.0.dev0"),
    ("1.0.1b0.dev0",       "major", "2.0.0.dev0"),
    ("1.0.1b0.dev3",       "major", "2.0.0.dev0"),
    ("1.0.1b2",            "major", "2.0.0.dev0"),
    ("1.0.1b2.dev0",       "major", "2.0.0.dev0"),
    ("1.0.1b2.dev3",       "major", "2.0.0.dev0"),
    ("1.0.1rc0",           "major", "2.0.0.dev0"),
    ("1.0.1rc0.dev0",      "major", "2.0.0.dev0"),
    ("1.0.1rc0.dev3",      "major", "2.0.0.dev0"),
    ("1.0.1rc2",           "major", "2.0.0.dev0"),
    ("1.0.1rc2.dev0",      "major", "2.0.0.dev0"),
    ("1.0.1rc2.dev3",      "major", "2.0.0.dev0"),
    ("1.0.1.post0",        "major", "2.0.0.dev0"),
    ("1.0.1.post0.dev0",   "major", "2.0.0.dev0"),
    ("1.0.1.post0.dev3",   "major", "2.0.0.dev0"),
    ("1.0.1.post2",        "major", "2.0.0.dev0"),
    ("1.0.1.post2.dev0",   "major", "2.0.0.dev0"),
    ("1.0.1.post2.dev3",   "major", "2.0.0.dev0"),

    # ── --minor (27 cells, all → 1.1.0.dev0) ──
    ("1.0.1",              "minor", "1.1.0.dev0"),
    ("1.0.1.dev0",         "minor", "1.1.0.dev0"),
    ("1.0.1.dev3",         "minor", "1.1.0.dev0"),
    ("1.0.1a0",            "minor", "1.1.0.dev0"),
    ("1.0.1a0.dev0",       "minor", "1.1.0.dev0"),
    ("1.0.1a0.dev3",       "minor", "1.1.0.dev0"),
    ("1.0.1a2",            "minor", "1.1.0.dev0"),
    ("1.0.1a2.dev0",       "minor", "1.1.0.dev0"),
    ("1.0.1a2.dev3",       "minor", "1.1.0.dev0"),
    ("1.0.1b0",            "minor", "1.1.0.dev0"),
    ("1.0.1b0.dev0",       "minor", "1.1.0.dev0"),
    ("1.0.1b0.dev3",       "minor", "1.1.0.dev0"),
    ("1.0.1b2",            "minor", "1.1.0.dev0"),
    ("1.0.1b2.dev0",       "minor", "1.1.0.dev0"),
    ("1.0.1b2.dev3",       "minor", "1.1.0.dev0"),
    ("1.0.1rc0",           "minor", "1.1.0.dev0"),
    ("1.0.1rc0.dev0",      "minor", "1.1.0.dev0"),
    ("1.0.1rc0.dev3",      "minor", "1.1.0.dev0"),
    ("1.0.1rc2",           "minor", "1.1.0.dev0"),
    ("1.0.1rc2.dev0",      "minor", "1.1.0.dev0"),
    ("1.0.1rc2.dev3",      "minor", "1.1.0.dev0"),
    ("1.0.1.post0",        "minor", "1.1.0.dev0"),
    ("1.0.1.post0.dev0",   "minor", "1.1.0.dev0"),
    ("1.0.1.post0.dev3",   "minor", "1.1.0.dev0"),
    ("1.0.1.post2",        "minor", "1.1.0.dev0"),
    ("1.0.1.post2.dev0",   "minor", "1.1.0.dev0"),
    ("1.0.1.post2.dev3",   "minor", "1.1.0.dev0"),

    # ── --patch (27 cells, all → 1.0.2.dev0) ──
    ("1.0.1",              "patch", "1.0.2.dev0"),
    ("1.0.1.dev0",         "patch", "1.0.2.dev0"),
    ("1.0.1.dev3",         "patch", "1.0.2.dev0"),
    ("1.0.1a0",            "patch", "1.0.2.dev0"),
    ("1.0.1a0.dev0",       "patch", "1.0.2.dev0"),
    ("1.0.1a0.dev3",       "patch", "1.0.2.dev0"),
    ("1.0.1a2",            "patch", "1.0.2.dev0"),
    ("1.0.1a2.dev0",       "patch", "1.0.2.dev0"),
    ("1.0.1a2.dev3",       "patch", "1.0.2.dev0"),
    ("1.0.1b0",            "patch", "1.0.2.dev0"),
    ("1.0.1b0.dev0",       "patch", "1.0.2.dev0"),
    ("1.0.1b0.dev3",       "patch", "1.0.2.dev0"),
    ("1.0.1b2",            "patch", "1.0.2.dev0"),
    ("1.0.1b2.dev0",       "patch", "1.0.2.dev0"),
    ("1.0.1b2.dev3",       "patch", "1.0.2.dev0"),
    ("1.0.1rc0",           "patch", "1.0.2.dev0"),
    ("1.0.1rc0.dev0",      "patch", "1.0.2.dev0"),
    ("1.0.1rc0.dev3",      "patch", "1.0.2.dev0"),
    ("1.0.1rc2",           "patch", "1.0.2.dev0"),
    ("1.0.1rc2.dev0",      "patch", "1.0.2.dev0"),
    ("1.0.1rc2.dev3",      "patch", "1.0.2.dev0"),
    ("1.0.1.post0",        "patch", "1.0.2.dev0"),
    ("1.0.1.post0.dev0",   "patch", "1.0.2.dev0"),
    ("1.0.1.post0.dev3",   "patch", "1.0.2.dev0"),
    ("1.0.1.post2",        "patch", "1.0.2.dev0"),
    ("1.0.1.post2.dev0",   "patch", "1.0.2.dev0"),
    ("1.0.1.post2.dev3",   "patch", "1.0.2.dev0"),

    # ── --alpha (9 valid, 18 errors) ──
    ("1.0.1",              "alpha", "1.0.1a0.dev0"),
    ("1.0.1.dev0",         "alpha", "1.0.1a0.dev0"),
    ("1.0.1.dev3",         "alpha", "1.0.1a0.dev0"),
    ("1.0.1a0",            "alpha", "1.0.1a1.dev0"),
    ("1.0.1a0.dev0",       "alpha", "1.0.1a1.dev0"),
    ("1.0.1a0.dev3",       "alpha", "1.0.1a1.dev0"),
    ("1.0.1a2",            "alpha", "1.0.1a3.dev0"),
    ("1.0.1a2.dev0",       "alpha", "1.0.1a3.dev0"),
    ("1.0.1a2.dev3",       "alpha", "1.0.1a3.dev0"),
    ("1.0.1b0",            "alpha", E),  # downgrade b→a
    ("1.0.1b0.dev0",       "alpha", E),
    ("1.0.1b0.dev3",       "alpha", E),
    ("1.0.1b2",            "alpha", E),
    ("1.0.1b2.dev0",       "alpha", E),
    ("1.0.1b2.dev3",       "alpha", E),
    ("1.0.1rc0",           "alpha", E),  # downgrade rc→a
    ("1.0.1rc0.dev0",      "alpha", E),
    ("1.0.1rc0.dev3",      "alpha", E),
    ("1.0.1rc2",           "alpha", E),
    ("1.0.1rc2.dev0",      "alpha", E),
    ("1.0.1rc2.dev3",      "alpha", E),
    ("1.0.1.post0",        "alpha", E),  # pre from post
    ("1.0.1.post0.dev0",   "alpha", E),
    ("1.0.1.post0.dev3",   "alpha", E),
    ("1.0.1.post2",        "alpha", E),
    ("1.0.1.post2.dev0",   "alpha", E),
    ("1.0.1.post2.dev3",   "alpha", E),

    # ── --beta (15 valid, 12 errors) ──
    ("1.0.1",              "beta", "1.0.1b0.dev0"),
    ("1.0.1.dev0",         "beta", "1.0.1b0.dev0"),
    ("1.0.1.dev3",         "beta", "1.0.1b0.dev0"),
    ("1.0.1a0",            "beta", "1.0.1b0.dev0"),
    ("1.0.1a0.dev0",       "beta", "1.0.1b0.dev0"),
    ("1.0.1a0.dev3",       "beta", "1.0.1b0.dev0"),
    ("1.0.1a2",            "beta", "1.0.1b0.dev0"),
    ("1.0.1a2.dev0",       "beta", "1.0.1b0.dev0"),
    ("1.0.1a2.dev3",       "beta", "1.0.1b0.dev0"),
    ("1.0.1b0",            "beta", "1.0.1b1.dev0"),
    ("1.0.1b0.dev0",       "beta", "1.0.1b1.dev0"),
    ("1.0.1b0.dev3",       "beta", "1.0.1b1.dev0"),
    ("1.0.1b2",            "beta", "1.0.1b3.dev0"),
    ("1.0.1b2.dev0",       "beta", "1.0.1b3.dev0"),
    ("1.0.1b2.dev3",       "beta", "1.0.1b3.dev0"),
    ("1.0.1rc0",           "beta", E),  # downgrade rc→b
    ("1.0.1rc0.dev0",      "beta", E),
    ("1.0.1rc0.dev3",      "beta", E),
    ("1.0.1rc2",           "beta", E),
    ("1.0.1rc2.dev0",      "beta", E),
    ("1.0.1rc2.dev3",      "beta", E),
    ("1.0.1.post0",        "beta", E),  # pre from post
    ("1.0.1.post0.dev0",   "beta", E),
    ("1.0.1.post0.dev3",   "beta", E),
    ("1.0.1.post2",        "beta", E),
    ("1.0.1.post2.dev0",   "beta", E),
    ("1.0.1.post2.dev3",   "beta", E),

    # ── --rc (21 valid, 6 errors) ──
    ("1.0.1",              "rc", "1.0.1rc0.dev0"),
    ("1.0.1.dev0",         "rc", "1.0.1rc0.dev0"),
    ("1.0.1.dev3",         "rc", "1.0.1rc0.dev0"),
    ("1.0.1a0",            "rc", "1.0.1rc0.dev0"),
    ("1.0.1a0.dev0",       "rc", "1.0.1rc0.dev0"),
    ("1.0.1a0.dev3",       "rc", "1.0.1rc0.dev0"),
    ("1.0.1a2",            "rc", "1.0.1rc0.dev0"),
    ("1.0.1a2.dev0",       "rc", "1.0.1rc0.dev0"),
    ("1.0.1a2.dev3",       "rc", "1.0.1rc0.dev0"),
    ("1.0.1b0",            "rc", "1.0.1rc0.dev0"),
    ("1.0.1b0.dev0",       "rc", "1.0.1rc0.dev0"),
    ("1.0.1b0.dev3",       "rc", "1.0.1rc0.dev0"),
    ("1.0.1b2",            "rc", "1.0.1rc0.dev0"),
    ("1.0.1b2.dev0",       "rc", "1.0.1rc0.dev0"),
    ("1.0.1b2.dev3",       "rc", "1.0.1rc0.dev0"),
    ("1.0.1rc0",           "rc", "1.0.1rc1.dev0"),
    ("1.0.1rc0.dev0",      "rc", "1.0.1rc1.dev0"),
    ("1.0.1rc0.dev3",      "rc", "1.0.1rc1.dev0"),
    ("1.0.1rc2",           "rc", "1.0.1rc3.dev0"),
    ("1.0.1rc2.dev0",      "rc", "1.0.1rc3.dev0"),
    ("1.0.1rc2.dev3",      "rc", "1.0.1rc3.dev0"),
    ("1.0.1.post0",        "rc", E),  # pre from post
    ("1.0.1.post0.dev0",   "rc", E),
    ("1.0.1.post0.dev3",   "rc", E),
    ("1.0.1.post2",        "rc", E),
    ("1.0.1.post2.dev0",   "rc", E),
    ("1.0.1.post2.dev3",   "rc", E),

    # ── --post (6 valid, 21 errors) ──
    ("1.0.1",              "post", E),  # no post suffix
    ("1.0.1.dev0",         "post", E),
    ("1.0.1.dev3",         "post", E),
    ("1.0.1a0",            "post", E),
    ("1.0.1a0.dev0",       "post", E),
    ("1.0.1a0.dev3",       "post", E),
    ("1.0.1a2",            "post", E),
    ("1.0.1a2.dev0",       "post", E),
    ("1.0.1a2.dev3",       "post", E),
    ("1.0.1b0",            "post", E),
    ("1.0.1b0.dev0",       "post", E),
    ("1.0.1b0.dev3",       "post", E),
    ("1.0.1b2",            "post", E),
    ("1.0.1b2.dev0",       "post", E),
    ("1.0.1b2.dev3",       "post", E),
    ("1.0.1rc0",           "post", E),
    ("1.0.1rc0.dev0",      "post", E),
    ("1.0.1rc0.dev3",      "post", E),
    ("1.0.1rc2",           "post", E),
    ("1.0.1rc2.dev0",      "post", E),
    ("1.0.1rc2.dev3",      "post", E),
    ("1.0.1.post0",        "post", "1.0.1.post1.dev0"),
    ("1.0.1.post0.dev0",   "post", "1.0.1.post1.dev0"),
    ("1.0.1.post0.dev3",   "post", "1.0.1.post1.dev0"),
    ("1.0.1.post2",        "post", "1.0.1.post3.dev0"),
    ("1.0.1.post2.dev0",   "post", "1.0.1.post3.dev0"),
    ("1.0.1.post2.dev3",   "post", "1.0.1.post3.dev0"),

    # ── --dev (27 cells, all valid) ──
    ("1.0.1",              "dev", "1.0.1.dev0"),
    ("1.0.1.dev0",         "dev", "1.0.1.dev1"),
    ("1.0.1.dev3",         "dev", "1.0.1.dev4"),
    ("1.0.1a0",            "dev", "1.0.1a0.dev0"),
    ("1.0.1a0.dev0",       "dev", "1.0.1a0.dev1"),
    ("1.0.1a0.dev3",       "dev", "1.0.1a0.dev4"),
    ("1.0.1a2",            "dev", "1.0.1a2.dev0"),
    ("1.0.1a2.dev0",       "dev", "1.0.1a2.dev1"),
    ("1.0.1a2.dev3",       "dev", "1.0.1a2.dev4"),
    ("1.0.1b0",            "dev", "1.0.1b0.dev0"),
    ("1.0.1b0.dev0",       "dev", "1.0.1b0.dev1"),
    ("1.0.1b0.dev3",       "dev", "1.0.1b0.dev4"),
    ("1.0.1b2",            "dev", "1.0.1b2.dev0"),
    ("1.0.1b2.dev0",       "dev", "1.0.1b2.dev1"),
    ("1.0.1b2.dev3",       "dev", "1.0.1b2.dev4"),
    ("1.0.1rc0",           "dev", "1.0.1rc0.dev0"),
    ("1.0.1rc0.dev0",      "dev", "1.0.1rc0.dev1"),
    ("1.0.1rc0.dev3",      "dev", "1.0.1rc0.dev4"),
    ("1.0.1rc2",           "dev", "1.0.1rc2.dev0"),
    ("1.0.1rc2.dev0",      "dev", "1.0.1rc2.dev1"),
    ("1.0.1rc2.dev3",      "dev", "1.0.1rc2.dev4"),
    ("1.0.1.post0",        "dev", "1.0.1.post0.dev0"),
    ("1.0.1.post0.dev0",   "dev", "1.0.1.post0.dev1"),
    ("1.0.1.post0.dev3",   "dev", "1.0.1.post0.dev4"),
    ("1.0.1.post2",        "dev", "1.0.1.post2.dev0"),
    ("1.0.1.post2.dev0",   "dev", "1.0.1.post2.dev1"),
    ("1.0.1.post2.dev3",   "dev", "1.0.1.post2.dev4"),
]
# fmt: on

# Sanity check
assert len(_MATRIX) == 216, f"Expected 216 cells, got {len(_MATRIX)}"

_VALID = [(v, bt, exp) for v, bt, exp in _MATRIX if exp != E]
_ERRORS = [(v, bt) for v, bt, exp in _MATRIX if exp == E]


class TestBumpMatrix:
    """27 versions × 8 bump types = 216 cells."""

    @pytest.mark.parametrize(
        "version,bump_type,expected",
        _VALID,
        ids=[f"{v}+{bt}" for v, bt, _ in _VALID],
    )
    def test_valid(self, version: str, bump_type: str, expected: str) -> None:
        pre_kind = _PRE_KIND_MAP.get(bump_type, "")
        validate_bump(version, bump_type, pre_kind)
        assert compute_bumped_version(version, bump_type=bump_type) == expected

    @pytest.mark.parametrize(
        "version,bump_type",
        _ERRORS,
        ids=[f"{v}+{bt}" for v, bt in _ERRORS],
    )
    def test_error(self, version: str, bump_type: str) -> None:
        pre_kind = _PRE_KIND_MAP.get(bump_type, "")
        with pytest.raises(ValueError):
            validate_bump(version, bump_type, pre_kind)
