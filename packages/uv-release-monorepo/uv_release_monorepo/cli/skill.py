"""The ``uvr skill init`` and ``uvr skill init --upgrade`` commands."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from ..shared.utils.toml import get_path, read_pyproject, write_pyproject
from ..shared.utils.cli import fatal
from .init import _editor_cmd, _read_base, _resolve_editor, _write_base


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

_SKILLS_TEMPLATE_DIR = files("uv_release_monorepo").joinpath("templates/skills")


def _load_skill_file(skill_name: str, rel_path: str) -> str:
    """Load a skill file from the bundled template directory."""
    base = Path(str(_SKILLS_TEMPLATE_DIR))
    path = base / skill_name / rel_path
    return path.read_text(encoding="utf-8")


def _store_skill_version(root: Path) -> None:
    """Store the current uvr package version as skill_version in [tool.uvr.config]."""
    from ..shared.utils.cli import __version__

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return
    doc = read_pyproject(pyproject)
    tool = doc.setdefault("tool", {})
    uvr = tool.setdefault("uvr", {})
    config = uvr.setdefault("config", {})
    config["skill_version"] = __version__
    # Remove legacy key if present
    config.pop("skill_init_commit", None)
    write_pyproject(pyproject, doc)


def cmd_skill_dispatch(args: argparse.Namespace) -> None:
    """Route to cmd_skill_init or cmd_skill_upgrade based on --upgrade flag."""
    if getattr(args, "upgrade", False):
        cmd_skill_upgrade(args)
    else:
        cmd_skill_init(args)


def cmd_skill_init(args: argparse.Namespace) -> None:
    """Copy bundled Claude Code skills into the current project."""
    from ..shared.utils.cli import __version__

    root = Path.cwd()
    base_only = getattr(args, "base_only", False)

    if base_only:
        # --base-only: write merge bases without touching actual files
        count = 0
        for skill_name in _SKILL_FILES:
            for rel_path in _SKILL_FILES[skill_name]:
                rel_dest = f".claude/skills/{skill_name}/{rel_path}"
                _write_base(root, rel_dest, _load_skill_file(skill_name, rel_path))
                count += 1
        print(f"OK: Wrote {count} merge bases for skills (uvr v{__version__})")
        return

    if not (root / ".git").exists():
        fatal("Not a git repository. Run from the repo root.")

    dest_base = root / ".claude" / "skills"
    force = getattr(args, "force", False)

    written = 0
    skipped = 0
    for skill_name in _SKILL_FILES:
        for rel_path in _SKILL_FILES[skill_name]:
            dest = dest_base / skill_name / rel_path
            if dest.exists() and not force:
                print(f"  skip  {skill_name}/{rel_path} (exists)")
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = _load_skill_file(skill_name, rel_path)
            dest.write_text(content, encoding="utf-8")
            # Save merge base
            rel_dest = f".claude/skills/{skill_name}/{rel_path}"
            _write_base(root, rel_dest, content)
            print(f"  write {skill_name}/{rel_path}")
            written += 1

    print()
    if written:
        _store_skill_version(root)
        from ..shared.utils.cli import __version__

        print(f"OK: Wrote {written} file(s) to .claude/skills/ (uvr v{__version__})")
    if skipped:
        print(f"  Skipped {skipped} existing file(s). Use --force to overwrite.")
    if not written and not skipped:
        print("Nothing to do.")
        return

    print()
    print("Next steps:")
    print("  1. Review .claude/skills/release/SKILL.md and tailor to your project")
    print("  2. Commit the skill files")
    print("  3. Use /release in Claude Code to start a release")


def cmd_skill_upgrade(args: argparse.Namespace) -> None:
    """Upgrade skill files using three-way merge from bundled templates."""
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
        and not _read_base(root, f".claude/skills/{name}/{rel_path}")
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
            uvx_cmd = f"uvx --from uv-release-monorepo=={stored_version} uvr skill init --base-only"
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
                    # Re-check — if bases now exist, three-way merge will be used
                    any_still_missing = any(
                        (dest_base / name / rel_path).exists()
                        and not _read_base(root, f".claude/skills/{name}/{rel_path}")
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
                _write_base(root, rel_dest, fresh_text)
                print(f"  new   {rel_dest}")
                new_files += 1
                written_files.append(str(dest))
                continue

            existing_text = dest.read_text(encoding="utf-8")
            if existing_text.rstrip() == fresh_text.rstrip():
                up_to_date += 1
                continue

            # Read merge base from .uvr/bases/ (empty string → two-way merge)
            base_text = _read_base(root, rel_dest)

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
            _write_base(root, rel_dest, fresh_text)
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
                _store_skill_version(root)
                for f in still_conflicted:
                    rel = str(Path(f).relative_to(root))
                    print(f"  Resolve markers in {rel}")
                return

    _store_skill_version(root)
    from ..shared.utils.cli import __version__

    print(f"\nUpgraded skills (uvr v{__version__}). Review and commit the changes.")
