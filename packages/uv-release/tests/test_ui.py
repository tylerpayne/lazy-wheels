"""Tests for pure helpers in `uv_release.ui`.

The Rich-rendered components (section, progress_lines, spinner, etc.) are
covered by the visual `uvr ui-demo` command. Here we just exercise the
parts where a wrong padding or missing key would silently misalign output.
"""

from __future__ import annotations

import pytest

from uv_release.ui.badge import _STYLES, _WIDTH, badge, badge_markup


class TestBadge:
    def test_known_kinds_pad_to_widest(self) -> None:
        # Every badge text should occupy exactly _WIDTH chars so columns
        # of mixed kinds line up.
        for kind in _STYLES:
            text = badge(kind)
            assert len(text.plain) == _WIDTH, (
                f"badge({kind!r}) was {len(text.plain)} chars, expected {_WIDTH}"
            )

    def test_width_is_widest_known_kind(self) -> None:
        assert _WIDTH == max(len(k) for k in _STYLES)

    def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown badge kind"):
            badge("nope")

    def test_markup_pads_and_styles(self) -> None:
        m = badge_markup("changed")
        assert m == f"[uvr.changed]{'changed':<{_WIDTH}}[/]"

    def test_markup_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown badge kind"):
            badge_markup("nope")


class TestKv:
    def test_aligns_keys_to_widest(self, capsys: pytest.CaptureFixture[str]) -> None:
        from uv_release.ui.kv import kv

        kv({"a": "1", "longer": "2", "mid": "3"})
        out = capsys.readouterr().out
        # Every line should have the value at the same column. With keys
        # padded to width 6 ("longer"), the value should start at the same
        # offset on every line.
        lines = [ln for ln in out.splitlines() if ln.strip()]
        # Find where the value digit appears on each line.
        positions = [ln.index(str(i + 1)) for i, ln in enumerate(lines)]
        assert len(set(positions)) == 1, f"misaligned: {positions}"

    def test_empty_is_noop(self, capsys: pytest.CaptureFixture[str]) -> None:
        from uv_release.ui.kv import kv

        kv({})
        assert capsys.readouterr().out == ""


class TestErrorBlock:
    def test_aligns_detail_keys(self, capsys: pytest.CaptureFixture[str]) -> None:
        from uv_release.ui.error import error

        error("summary", detail={"short": "a", "longer-key": "b"})
        # Errors go to stderr so they're separable from regular output.
        out = capsys.readouterr().err
        lines = [ln for ln in out.splitlines() if ln.strip()]
        a_pos = lines[1].rindex("a")
        b_pos = lines[2].rindex("b")
        assert a_pos == b_pos

    def test_fixes_under_section_header(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from uv_release.ui.error import error

        error("x", fixes=["one", "two"])
        out = capsys.readouterr().err
        # Fix lives under a `Fix\n---` section header; commands sit indented
        # below as plain lines (no per-line lead).
        assert "Fix\n---" in out
        cmd_lines = [ln for ln in out.splitlines() if ln.startswith("  ")]
        assert "  one" in cmd_lines
        assert "  two" in cmd_lines


class TestPipeline:
    def test_aligns_route_sources(self, capsys: pytest.CaptureFixture[str]) -> None:
        from uv_release.ui.pipeline import Route, Step, pipeline

        pipeline(
            [
                Step(
                    name="publish",
                    routes=(
                        Route(src="short", dst="pypi"),
                        Route(src="much-longer", dst="ghcr.io"),
                    ),
                )
            ]
        )
        out = capsys.readouterr().out
        # Both arrows should sit in the same column.
        arrow_lines = [ln for ln in out.splitlines() if "→" in ln]
        assert len(arrow_lines) == 2
        positions = [ln.index("→") for ln in arrow_lines]
        assert len(set(positions)) == 1, f"arrows misaligned: {positions}"
