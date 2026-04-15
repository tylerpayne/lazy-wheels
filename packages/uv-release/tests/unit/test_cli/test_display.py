"""Tests for CLI display formatting."""

from __future__ import annotations

from uv_release.cli.display import format_table


class TestFormatTable:
    def test_empty_rows_returns_empty(self) -> None:
        result = format_table(("A", "B"), [])
        assert result == []

    def test_single_row_aligned(self) -> None:
        headers = ("NAME", "VERSION")
        rows = [("alpha", "1.0.0")]
        lines = format_table(headers, rows)
        assert len(lines) == 2
        # Header line
        assert "NAME" in lines[0]
        assert "VERSION" in lines[0]
        # Data line
        assert "alpha" in lines[1]
        assert "1.0.0" in lines[1]

    def test_columns_aligned_to_widest(self) -> None:
        headers = ("A", "B")
        rows = [("short", "x"), ("much-longer-name", "y")]
        lines = format_table(headers, rows)
        # All lines should have the same alignment
        # The "B" column should start at the same position in each line
        b_positions = [
            line.index("x") if "x" in line else line.index("y") for line in lines[1:]
        ]
        assert b_positions[0] == b_positions[1]

    def test_header_wider_than_data(self) -> None:
        headers = ("VERY_LONG_HEADER", "B")
        rows = [("a", "b")]
        lines = format_table(headers, rows)
        # Data should be padded to header width
        assert len(lines[0]) == len(lines[1])
