"""The ``uvr skill init`` and ``uvr skill init --upgrade`` commands."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from ._common import _fatal
from .init import _editor_cmd, _get_base_text, _git_commit_and_record, _resolve_editor


_SKILL_FILES: dict[str, list[str]] = {
    "release": [
        "SKILL.md",
        "references/cmd-init.md",
        "references/cmd-install.md",
        "references/cmd-release.md",
        "references/cmd-runners.md",
        "references/cmd-skill-init.md",
        "references/cmd-status.md",
        "references/cmd-validate.md",
        "references/custom-jobs.md",
        "references/dev-releases.md",
        "references/pipeline.md",
        "references/post-releases.md",
        "references/pre-releases.md",
        "references/release-plan.md",
        "references/troubleshooting.md",
    ],
}


def _skill_root() -> Path:
    """Return the root of the bundled skills directory as a concrete Path."""
    return Path(str(files("uv_release_monorepo").joinpath("skills")))


def _copy_skill(name: str, dest_base: Path, *, force: bool) -> tuple[int, int]:
    """Copy a single skill's files.  Returns *(written, skipped)* counts."""
    src_root = _skill_root() / name
    written = skipped = 0
    for rel_path in _SKILL_FILES[name]:
        src = src_root / rel_path
        dest = dest_base / name / rel_path
        if dest.exists() and not force:
            print(f"  skip  {name}/{rel_path} (exists)")
            skipped += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  write {name}/{rel_path}")
        written += 1
    return written, skipped


def cmd_skill_init(args: argparse.Namespace) -> None:
    """Copy bundled Claude Code skills into the current project."""
    root = Path.cwd()

    if not (root / ".git").exists():
        _fatal("Not a git repository. Run from the repo root.")

    dest_base = root / ".claude" / "skills"
    force = getattr(args, "force", False)

    written = 0
    skipped = 0
    for name in _SKILL_FILES:
        w, s = _copy_skill(name, dest_base, force=force)
        written += w
        skipped += s

    print()
    if written:
        print(f"OK: Wrote {written} file(s) to .claude/skills/")
    if skipped:
        print(f"  Skipped {skipped} existing file(s). Use --force to overwrite.")
    if not written and not skipped:
        print("Nothing to do.")
        return

    # Commit and record
    all_files = [
        str(dest_base / name / rel_path)
        for name in _SKILL_FILES
        for rel_path in _SKILL_FILES[name]
        if (dest_base / name / rel_path).exists()
    ]
    _git_commit_and_record(
        root, all_files, "chore: uvr skill init", "skill_init_commit"
    )

    print()
    print("Next steps:")
    print("  1. Review .claude/skills/release/SKILL.md and tailor to your project")
    print("  2. Use /release in Claude Code to start a release")


def cmd_skill_upgrade(args: argparse.Namespace) -> None:
    """Upgrade skill files using three-way merge."""
    root = Path.cwd()

    if not (root / ".git").exists():
        _fatal("Not a git repository. Run from the repo root.")

    dest_base = root / ".claude" / "skills"
    src_root = _skill_root()

    # Check for uncommitted changes in skill files
    skill_paths = [
        str(dest_base / name / rel_path)
        for name in _SKILL_FILES
        for rel_path in _SKILL_FILES[name]
        if (dest_base / name / rel_path).exists()
    ]
    if skill_paths:
        result = subprocess.run(
            ["git", "diff", "--quiet", "--"] + skill_paths,
            capture_output=True,
        )
        if result.returncode != 0:
            _fatal(
                "Skill files have uncommitted changes.\n"
                "  Commit or stash them before upgrading."
            )

    upgraded = 0
    up_to_date = 0
    new_files = 0
    has_any_conflicts = False
    written_files: list[str] = []

    for name in _SKILL_FILES:
        for rel_path in _SKILL_FILES[name]:
            src = src_root / name / rel_path
            dest = dest_base / name / rel_path
            fresh_text = src.read_text(encoding="utf-8")
            rel_dest = f".claude/skills/{name}/{rel_path}"

            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(fresh_text, encoding="utf-8")
                print(f"  new   {rel_dest}")
                new_files += 1
                written_files.append(str(dest))
                continue

            existing_text = dest.read_text(encoding="utf-8")
            if existing_text.rstrip() == fresh_text.rstrip():
                up_to_date += 1
                continue

            # Three-way merge
            base_text = _get_base_text(root, rel_dest, "skill_init_commit")

            with (
                tempfile.NamedTemporaryFile(
                    mode="w", suffix=".md", prefix="base-", delete=False
                ) as base_f,
                tempfile.NamedTemporaryFile(
                    mode="w", suffix=".md", prefix="fresh-", delete=False
                ) as fresh_f,
            ):
                base_f.write(base_text)
                base_f.flush()
                fresh_f.write(fresh_text)
                fresh_f.flush()
                base_path = Path(base_f.name)
                fresh_path = Path(fresh_f.name)

            try:
                result = subprocess.run(
                    [
                        "git",
                        "merge-file",
                        "-p",
                        "-L",
                        "current",
                        "-L",
                        "base",
                        "-L",
                        "bundled",
                        str(dest),
                        str(base_path),
                        str(fresh_path),
                    ],
                    capture_output=True,
                    text=True,
                )
            finally:
                base_path.unlink(missing_ok=True)
                fresh_path.unlink(missing_ok=True)

            if result.returncode < 0:
                print(f"  ERROR {rel_dest}: git merge-file failed")
                continue

            merged_text = result.stdout
            has_conflicts = result.returncode > 0

            if merged_text.rstrip() == existing_text.rstrip():
                up_to_date += 1
                continue

            dest.write_text(merged_text)
            marker = " (conflicts)" if has_conflicts else ""
            print(f"  merge {rel_dest}{marker}")
            upgraded += 1
            written_files.append(str(dest))
            if has_conflicts:
                has_any_conflicts = True

    print()
    total = upgraded + new_files
    if total == 0:
        print("Already up to date.")
        return

    parts = []
    if upgraded:
        parts.append(f"{upgraded} merged")
    if new_files:
        parts.append(f"{new_files} new")
    print(f"OK: {', '.join(parts)}")

    if has_any_conflicts:
        # Offer editor for conflict resolution
        conflict_files = [f for f in written_files if "<<<<<<" in Path(f).read_text()]
        editor = _resolve_editor(args, root)
        for f in conflict_files:
            rel = str(Path(f).relative_to(root))
            print(f"\n  Conflicts in {rel}")
            prompt = (
                f"  Open in {editor} to resolve? [Y/n/editor] "
                if editor
                else "  Editor to resolve? [n/editor] "
            )
            try:
                answer = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer.lower() not in ("n", "no", ""):
                chosen = editor if answer.lower() in ("y", "yes") else answer
                if chosen:
                    subprocess.run([*_editor_cmd(chosen), f])
            elif editor and answer == "":
                subprocess.run([*_editor_cmd(editor), f])

        # Check if all conflicts resolved
        still_conflicted = [
            f for f in conflict_files if "<<<<<<" in Path(f).read_text()
        ]
        if still_conflicted:
            print("\nUnresolved conflicts remain.")
            try:
                answer = input("Revert all changes? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = ""
            if answer not in ("n", "no"):
                subprocess.run(
                    ["git", "checkout", "--"] + written_files, capture_output=True
                )
                print("Reverted. No changes applied.")
                return
            else:
                for f in still_conflicted:
                    rel = str(Path(f).relative_to(root))
                    print(f"  Resolve markers in {rel}")
                return

    _git_commit_and_record(
        root,
        written_files,
        "chore: uvr skill init --upgrade",
        "skill_init_commit",
    )
