"""Three-way merge logic using the git adapter."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..git import GitRepo
from ..types import MergeResult


def three_way_merge(
    current: Path,
    base: Path,
    template: Path,
) -> MergeResult:
    """Perform a three-way merge of a single file.

    Returns a MergeResult describing what happened.
    """
    if not current.exists():
        current.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, current)
        return MergeResult(path=str(current), has_conflicts=False, is_new=True)

    if not base.exists():
        if current.read_text() == template.read_text():
            return MergeResult(path=str(current), has_conflicts=False, is_new=False)
        return MergeResult(path=str(current), has_conflicts=True, is_new=False)

    repo = GitRepo()
    merged_content, has_conflicts = repo.merge_file(current, base, template)
    current.write_text(merged_content)

    return MergeResult(path=str(current), has_conflicts=has_conflicts, is_new=False)


def three_way_merge_directory(
    current_dir: Path,
    base_dir: Path,
    template_dir: Path,
) -> list[MergeResult]:
    """Three-way merge all files in a directory tree.

    Walks the template directory and merges each file against its
    counterpart in current and base. New files (in template but not
    current) are copied. Files in current but not template are left alone.
    """
    results: list[MergeResult] = []

    for template_file in sorted(template_dir.rglob("*")):
        if template_file.is_dir():
            continue

        relative = template_file.relative_to(template_dir)
        current_file = current_dir / relative
        base_file = base_dir / relative

        result = three_way_merge(current_file, base_file, template_file)
        results.append(result)

    return results
