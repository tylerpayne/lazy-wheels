"""Tests for lazy_wheels.versions."""

from __future__ import annotations


from lazy_wheels.versions import bump_patch, parse_version


class TestParseVersion:
    def test_full_semver(self) -> None:
        v = parse_version("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_two_part_version(self) -> None:
        v = parse_version("1.2")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 0

    def test_single_part_version(self) -> None:
        v = parse_version("5")
        assert v.major == 5
        assert v.minor == 0
        assert v.patch == 0

    def test_zero_version(self) -> None:
        v = parse_version("0.0.0")
        assert v.major == 0
        assert v.minor == 0
        assert v.patch == 0


class TestBumpPatch:
    def test_bump_full_version(self) -> None:
        assert bump_patch("1.2.3") == "1.2.4"

    def test_bump_two_part(self) -> None:
        assert bump_patch("1.2") == "1.2.1"

    def test_bump_single_part(self) -> None:
        assert bump_patch("1") == "1.0.1"

    def test_bump_zero(self) -> None:
        assert bump_patch("0.0.0") == "0.0.1"

    def test_bump_high_patch(self) -> None:
        assert bump_patch("1.0.99") == "1.0.100"
