"""Tests for uv_release_monorepo.shared.utils.versions."""

from __future__ import annotations

from uv_release_monorepo.shared.utils.versions import (
    bump_dev,
    bump_patch,
    get_base_version,
    is_dev,
    make_dev,
    make_post,
    make_pre,
    next_post_number,
    next_pre_number,
    parse_tag_version,
    parse_version,
    strip_dev,
    strip_version,
)


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

    def test_strips_dev(self) -> None:
        v = parse_version("1.2.3.dev0")
        assert v.patch == 3

    def test_strips_pre(self) -> None:
        v = parse_version("1.2.3a1")
        assert v.patch == 3

    def test_strips_post(self) -> None:
        v = parse_version("1.2.3.post0")
        assert v.patch == 3


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

    def test_bump_strips_dev(self) -> None:
        assert bump_patch("1.2.3.dev0") == "1.2.4"

    def test_bump_strips_pre(self) -> None:
        assert bump_patch("1.2.3a1") == "1.2.4"


class TestStripDev:
    def test_strips_dev0(self) -> None:
        assert strip_dev("1.2.3.dev0") == "1.2.3"

    def test_strips_devN(self) -> None:
        assert strip_dev("1.2.3.dev5") == "1.2.3"

    def test_no_dev(self) -> None:
        assert strip_dev("1.2.3") == "1.2.3"

    def test_post_dev(self) -> None:
        assert strip_dev("1.2.3.post0.dev0") == "1.2.3.post0"


class TestMakeDev:
    def test_adds_dev0(self) -> None:
        assert make_dev("1.2.3") == "1.2.3.dev0"

    def test_idempotent(self) -> None:
        assert make_dev("1.2.3.dev0") == "1.2.3.dev0"

    def test_replaces_devN(self) -> None:
        assert make_dev("1.2.3.dev5") == "1.2.3.dev0"

    def test_post_version(self) -> None:
        assert make_dev("1.2.3.post0") == "1.2.3.post0.dev0"


class TestBumpDev:
    def test_bump_dev0(self) -> None:
        assert bump_dev("1.2.3.dev0") == "1.2.3.dev1"

    def test_bump_dev5(self) -> None:
        assert bump_dev("1.2.3.dev5") == "1.2.3.dev6"

    def test_no_dev_adds_dev0(self) -> None:
        assert bump_dev("1.2.3") == "1.2.3.dev0"


class TestClassifiers:
    def test_is_dev(self) -> None:
        assert is_dev("1.2.3.dev0") is True
        assert is_dev("1.2.3") is False
        assert is_dev("1.2.3a0") is False


class TestStripVersion:
    def test_dev_only(self) -> None:
        assert strip_version("1.2.3.dev0", dev=True) == "1.2.3"

    def test_pre_only(self) -> None:
        assert strip_version("1.2.3a1", pre=True) == "1.2.3"

    def test_post_only(self) -> None:
        assert strip_version("1.2.3.post0", post=True) == "1.2.3"

    def test_dev_and_pre(self) -> None:
        assert strip_version("1.2.3rc1.dev0", dev=True, pre=True) == "1.2.3"

    def test_dev_and_post(self) -> None:
        assert strip_version("1.2.3.post0.dev0", dev=True, post=True) == "1.2.3"

    def test_all(self) -> None:
        assert (
            strip_version("1.2.3.post0.dev0", dev=True, pre=True, post=True) == "1.2.3"
        )

    def test_no_flags_is_noop(self) -> None:
        assert strip_version("1.2.3rc1.dev0") == "1.2.3rc1.dev0"

    def test_dev_leaves_pre(self) -> None:
        assert strip_version("1.2.3rc1.dev0", dev=True) == "1.2.3rc1"

    def test_pre_alone_on_pre_dev_is_noop(self) -> None:
        # pre regex requires suffix at end; .dev0 blocks it — use dev=True too
        assert strip_version("1.2.3a1.dev0", pre=True) == "1.2.3a1.dev0"

    def test_pre_alone_on_bare_pre(self) -> None:
        assert strip_version("1.2.3a1", pre=True) == "1.2.3"


class TestGetBaseVersion:
    def test_plain(self) -> None:
        assert get_base_version("1.2.3") == "1.2.3"

    def test_dev(self) -> None:
        assert get_base_version("1.2.3.dev0") == "1.2.3"

    def test_pre(self) -> None:
        assert get_base_version("1.2.3a1") == "1.2.3"
        assert get_base_version("1.2.3b0") == "1.2.3"
        assert get_base_version("1.2.3rc2") == "1.2.3"

    def test_post(self) -> None:
        assert get_base_version("1.2.3.post0") == "1.2.3"

    def test_post_dev(self) -> None:
        assert get_base_version("1.2.3.post0.dev0") == "1.2.3"


class TestMakePre:
    def test_alpha(self) -> None:
        assert make_pre("1.2.3.dev2", "a") == "1.2.3a0"

    def test_beta(self) -> None:
        assert make_pre("1.2.3.dev0", "b", 1) == "1.2.3b1"

    def test_rc(self) -> None:
        assert make_pre("1.2.3.dev0", "rc", 2) == "1.2.3rc2"


class TestMakePost:
    def test_post0(self) -> None:
        assert make_post("1.2.3") == "1.2.3.post0"

    def test_post1(self) -> None:
        assert make_post("1.2.3", 1) == "1.2.3.post1"


class TestNextPreNumber:
    def test_no_existing(self) -> None:
        assert next_pre_number([], "pkg", "a") == 0

    def test_increments(self) -> None:
        tags = ["pkg/v1.0.0a0", "pkg/v1.0.0a1"]
        assert next_pre_number(tags, "pkg", "a") == 2

    def test_different_kind_ignored(self) -> None:
        tags = ["pkg/v1.0.0a0", "pkg/v1.0.0b0"]
        assert next_pre_number(tags, "pkg", "a") == 1

    def test_different_pkg_ignored(self) -> None:
        tags = ["other/v1.0.0a0", "other/v1.0.0a1"]
        assert next_pre_number(tags, "pkg", "a") == 0


class TestNextPostNumber:
    def test_no_existing(self) -> None:
        assert next_post_number([], "pkg") == 0

    def test_increments(self) -> None:
        tags = ["pkg/v1.0.0.post0"]
        assert next_post_number(tags, "pkg") == 1

    def test_different_pkg_ignored(self) -> None:
        tags = ["other/v1.0.0.post0"]
        assert next_post_number(tags, "pkg") == 0


class TestParseTagVersion:
    def test_simple_tag(self) -> None:
        assert parse_tag_version("pkg/v1.0.0") == "1.0.0"

    def test_dev_tag(self) -> None:
        assert parse_tag_version("my-pkg/v2.3.4.dev0") == "2.3.4.dev0"

    def test_hyphenated_name(self) -> None:
        assert parse_tag_version("my-long-pkg/v0.1.0") == "0.1.0"
