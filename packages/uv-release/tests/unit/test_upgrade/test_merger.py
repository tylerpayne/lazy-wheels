"""Tests for three-way merge logic."""

from __future__ import annotations

from pathlib import Path


from uv_release.upgrade.merge import three_way_merge, three_way_merge_directory
from uv_release.types import MergeResult


class TestThreeWayMerge:
    def test_no_changes(self, tmp_path: Path) -> None:
        """current == base == template → no-op."""
        content = "line 1\nline 2\n"
        current = tmp_path / "current.yml"
        base = tmp_path / "base.yml"
        template = tmp_path / "template.yml"
        current.write_text(content)
        base.write_text(content)
        template.write_text(content)

        result = three_way_merge(current, base, template)
        assert isinstance(result, MergeResult)
        assert result.has_conflicts is False
        assert result.is_new is False

    def test_user_edited_template_unchanged(self, tmp_path: Path) -> None:
        """User edited, template unchanged → keep user edits."""
        base = tmp_path / "base.yml"
        current = tmp_path / "current.yml"
        template = tmp_path / "template.yml"
        base.write_text("line 1\nline 2\n")
        current.write_text("line 1\nline 2 modified\n")
        template.write_text("line 1\nline 2\n")

        result = three_way_merge(current, base, template)
        assert result.has_conflicts is False
        # Current file should still have user's edits
        assert "modified" in current.read_text()

    def test_template_changed_user_didnt(self, tmp_path: Path) -> None:
        """Template changed, user didn't edit → apply template."""
        base = tmp_path / "base.yml"
        current = tmp_path / "current.yml"
        template = tmp_path / "template.yml"
        base.write_text("line 1\nline 2\n")
        current.write_text("line 1\nline 2\n")
        template.write_text("line 1\nline 2 upgraded\n")

        result = three_way_merge(current, base, template)
        assert result.has_conflicts is False
        assert "upgraded" in current.read_text()

    def test_both_changed_no_conflict(self, tmp_path: Path) -> None:
        """Both changed different lines → clean merge."""
        base = tmp_path / "base.yml"
        current = tmp_path / "current.yml"
        template = tmp_path / "template.yml"
        base.write_text("line 1\nline 2\nline 3\n")
        current.write_text("line 1 user\nline 2\nline 3\n")
        template.write_text("line 1\nline 2\nline 3 template\n")

        result = three_way_merge(current, base, template)
        assert result.has_conflicts is False
        merged = current.read_text()
        assert "user" in merged
        assert "template" in merged

    def test_both_changed_conflict(self, tmp_path: Path) -> None:
        """Both changed same line → has_conflicts=True."""
        base = tmp_path / "base.yml"
        current = tmp_path / "current.yml"
        template = tmp_path / "template.yml"
        base.write_text("line 1\n")
        current.write_text("line 1 user\n")
        template.write_text("line 1 template\n")

        result = three_way_merge(current, base, template)
        assert result.has_conflicts is True

    def test_new_file(self, tmp_path: Path) -> None:
        """No current file → is_new=True, template content written."""
        current = tmp_path / "new_file.yml"
        base = tmp_path / "base.yml"  # doesn't exist either
        template = tmp_path / "template.yml"
        template.write_text("new content\n")

        result = three_way_merge(current, base, template)
        assert result.is_new is True
        assert result.has_conflicts is False
        assert current.read_text() == "new content\n"

    def test_missing_base_two_way_fallback(self, tmp_path: Path) -> None:
        """No base file → two-way merge (current vs template)."""
        current = tmp_path / "current.yml"
        base = tmp_path / "base.yml"  # doesn't exist
        template = tmp_path / "template.yml"
        current.write_text("current content\n")
        template.write_text("template content\n")

        # Two-way merge: if they differ, conflict
        result = three_way_merge(current, base, template)
        assert result.has_conflicts is True


class TestThreeWayMergeDirectory:
    def test_merges_all_files_in_template(self, tmp_path: Path) -> None:
        """All files in template dir get merged."""
        current_dir = tmp_path / "current"
        base_dir = tmp_path / "base"
        template_dir = tmp_path / "template"

        for d in (current_dir, base_dir, template_dir):
            d.mkdir()
            (d / "a.md").write_text("line a\n")
            (d / "b.md").write_text("line b\n")

        results = three_way_merge_directory(current_dir, base_dir, template_dir)
        assert len(results) == 2
        assert all(not r.has_conflicts for r in results)

    def test_new_file_in_template_copied(self, tmp_path: Path) -> None:
        """File in template but not current gets copied."""
        current_dir = tmp_path / "current"
        base_dir = tmp_path / "base"
        template_dir = tmp_path / "template"

        current_dir.mkdir()
        base_dir.mkdir()
        template_dir.mkdir()
        (template_dir / "new.md").write_text("new content\n")

        results = three_way_merge_directory(current_dir, base_dir, template_dir)
        assert len(results) == 1
        assert results[0].is_new is True
        assert (current_dir / "new.md").read_text() == "new content\n"

    def test_nested_directories(self, tmp_path: Path) -> None:
        """Files in subdirectories are merged too."""
        current_dir = tmp_path / "current"
        base_dir = tmp_path / "base"
        template_dir = tmp_path / "template"

        for d in (current_dir, base_dir, template_dir):
            (d / "sub").mkdir(parents=True)
            (d / "top.md").write_text("top\n")
            (d / "sub" / "nested.md").write_text("nested\n")

        results = three_way_merge_directory(current_dir, base_dir, template_dir)
        assert len(results) == 2

    def test_current_only_files_left_alone(self, tmp_path: Path) -> None:
        """Files in current but not template are not touched."""
        current_dir = tmp_path / "current"
        base_dir = tmp_path / "base"
        template_dir = tmp_path / "template"

        current_dir.mkdir()
        base_dir.mkdir()
        template_dir.mkdir()
        (current_dir / "user_file.md").write_text("user content\n")
        (template_dir / "template_file.md").write_text("template\n")

        results = three_way_merge_directory(current_dir, base_dir, template_dir)
        assert len(results) == 1  # only template_file merged
        assert (current_dir / "user_file.md").read_text() == "user content\n"
