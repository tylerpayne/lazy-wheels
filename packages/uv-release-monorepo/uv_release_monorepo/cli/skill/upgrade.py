"""The ``uvr skill init --upgrade`` command."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from ...shared.utils.cli import fatal
from ...shared.utils.toml import get_path, read_pyproject
from .._args import CommandArgs
from .._upgrade import editor_cmd, read_base, resolve_editor, write_base
from .init import _SKILL_FILES, _load_skill_file, _store_skill_version


class SkillUpgradeArgs(CommandArgs):
    """Typed arguments for ``uvr skill init --upgrade``."""

    editor: str | None = None


def cmd_skill_upgrade(args: argparse.Namespace) -> None:
    """Upgrade skill files using three-way merge from bundled templates."""
    parsed = SkillUpgradeArgs.from_namespace(args)
    root = Path.cwd()

    if not (root / ".git").exists():
        fatal("Not a git repository. Run from the repo root.")

    dest_base = root / ".claude" / "skills"

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
            fatal(
                "Skill files have uncommitted changes.\n"
                "  Commit or stash them before upgrading."
            )

    # Check if any existing skill files are missing merge bases
    any_missing_base = any(
        (dest_base / name / rel_path).exists()
        and not read_base(root, f".claude/skills/{name}/{rel_path}")
        for name in _SKILL_FILES
        for rel_path in _SKILL_FILES[name]
    )
    if any_missing_base:
        pyproject = root / "pyproject.toml"
        stored_version = ""
        if pyproject.exists():
            stored_version = get_path(
                read_pyproject(pyproject),
                "tool",
                "uvr",
                "config",
                "skill_version",
                default="",
            )
        if stored_version:
            uvx_cmd = (
                f"uvx --from uv-release=={stored_version} uvr skill init --base-only"
            )
            print(
                f"No merge bases found for skills. For a cleaner upgrade, recover them first:\n"
                f"  {uvx_cmd}\n"
                f"  uvr skill init --upgrade\n"
            )
            try:
                run_it = input("Run the uvx command above? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                run_it = ""
            if run_it == "y":
                result = subprocess.run(uvx_cmd, shell=True)
                if result.returncode == 0:
                    # Re-check -- if bases now exist, three-way merge will be used
                    any_still_missing = any(
                        (dest_base / name / rel_path).exists()
                        and not read_base(root, f".claude/skills/{name}/{rel_path}")
                        for name in _SKILL_FILES
                        for rel_path in _SKILL_FILES[name]
                    )
                    if not any_still_missing:
                        print("Bases recovered. Proceeding with three-way merge.")
            else:
                try:
                    answer = (
                        input("Continue with two-way merge? [y/N] ").strip().lower()
                    )
                except (EOFError, KeyboardInterrupt):
                    answer = ""
                if answer != "y":
                    return

    upgraded = 0
    up_to_date = 0
    new_files = 0
    has_any_conflicts = False
    written_files: list[str] = []

    for skill_name in _SKILL_FILES:
        for rel_path in _SKILL_FILES[skill_name]:
            dest = dest_base / skill_name / rel_path
            fresh_text = _load_skill_file(skill_name, rel_path)
            rel_dest = f".claude/skills/{skill_name}/{rel_path}"

            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(fresh_text, encoding="utf-8")
                write_base(root, rel_dest, fresh_text)
                print(f"  new   {rel_dest}")
                new_files += 1
                written_files.append(str(dest))
                continue

            existing_text = dest.read_text(encoding="utf-8")
            if existing_text.rstrip() == fresh_text.rstrip():
                up_to_date += 1
                continue

            # Read merge base from .uvr/bases/ (empty string -> two-way merge)
            base_text = read_base(root, rel_dest)

            # Three-way merge (falls back to two-way if base is empty)
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
            write_base(root, rel_dest, fresh_text)
            marker = " (conflicts)" if has_conflicts else ""
            print(f"  merge {rel_dest}{marker}")
            upgraded += 1
            written_files.append(str(dest))
            if has_conflicts:
                has_any_conflicts = True

    print()
    total = upgraded + new_files
    if total == 0:
        _store_skill_version(root)
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
        cli_editor = parsed.editor
        editor = resolve_editor(cli_editor, root)
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
                    subprocess.run([*editor_cmd(chosen), f])
            elif editor and answer == "":
                subprocess.run([*editor_cmd(editor), f])

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
                _store_skill_version(root)
                for f in still_conflicted:
                    rel = str(Path(f).relative_to(root))
                    print(f"  Resolve markers in {rel}")
                return

    _store_skill_version(root)
    from ...shared.utils.cli import __version__

    print(f"\nUpgraded skills (uvr v{__version__}). Review and commit the changes.")
