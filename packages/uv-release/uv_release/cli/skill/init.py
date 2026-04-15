"""The ``uvr skill init`` and ``uvr skill init --upgrade`` commands."""

from __future__ import annotations

import argparse
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import tomlkit

from .._args import CommandArgs
from .._upgrade import (
    editor_cmd,
    read_base,
    resolve_editor,
    three_way_merge,
    write_base,
)

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
        "references/cmd-wheels.md",
        "references/custom-jobs.md",
        "references/dev-releases.md",
        "references/pipeline.md",
        "references/post-releases.md",
        "references/pre-releases.md",
        "references/release-plan.md",
        "references/troubleshooting.md",
    ],
}

_SKILLS_TEMPLATE_DIR = files("uv_release").joinpath("templates/skills")


class SkillInitArgs(CommandArgs):
    """Typed arguments for ``uvr skill init``."""

    force: bool = False
    upgrade: bool = False
    base_only: bool = False
    editor: str | None = None


def _load_skill_file(skill_name: str, rel_path: str) -> str:
    """Load a skill file from the bundled template directory."""
    base = Path(str(_SKILLS_TEMPLATE_DIR))
    path = base / skill_name / rel_path
    return path.read_text(encoding="utf-8")


def _uvr_version() -> str:
    from importlib.metadata import version

    return version("uv_release")


def _store_skill_version(root: Path) -> None:
    """Store the current uvr version as skill_version in [tool.uvr.config]."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return
    doc = tomlkit.loads(pyproject.read_text())
    tool = doc.setdefault("tool", {})
    uvr = tool.setdefault("uvr", {})
    config = uvr.setdefault("config", {})
    config["skill_version"] = _uvr_version()
    pyproject.write_text(tomlkit.dumps(doc))


def cmd_skill_init(args: argparse.Namespace) -> None:
    """Copy bundled Claude Code skills into the current project."""
    parsed = SkillInitArgs.from_namespace(args)
    root = Path.cwd()
    ver = _uvr_version()

    if parsed.base_only:
        count = 0
        for skill_name, file_list in _SKILL_FILES.items():
            for rel_path in file_list:
                rel_dest = f".claude/skills/{skill_name}/{rel_path}"
                write_base(root, rel_dest, _load_skill_file(skill_name, rel_path))
                count += 1
        print(f"OK: Wrote {count} merge bases for skills (uvr v{ver})")
        return

    if not (root / ".git").exists():
        print("ERROR: Not a git repository. Run from the repo root.", file=sys.stderr)
        sys.exit(1)

    dest_base = root / ".claude" / "skills"

    written = 0
    skipped = 0
    for skill_name, file_list in _SKILL_FILES.items():
        for rel_path in file_list:
            dest = dest_base / skill_name / rel_path
            if dest.exists() and not parsed.force:
                print(f"  skip  {skill_name}/{rel_path} (exists)")
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = _load_skill_file(skill_name, rel_path)
            dest.write_text(content, encoding="utf-8")
            rel_dest = f".claude/skills/{skill_name}/{rel_path}"
            write_base(root, rel_dest, content)
            print(f"  write {skill_name}/{rel_path}")
            written += 1

    print()
    if written:
        _store_skill_version(root)
        print(f"OK: Wrote {written} file(s) to .claude/skills/ (uvr v{ver})")
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
    """Upgrade skill files via three-way merge."""
    parsed = SkillInitArgs.from_namespace(args)
    root = Path.cwd()
    ver = _uvr_version()
    dest_base = root / ".claude" / "skills"

    written = 0
    conflicts = 0
    up_to_date = 0

    for skill_name, file_list in _SKILL_FILES.items():
        for rel_path in file_list:
            dest = dest_base / skill_name / rel_path
            rel_dest = f".claude/skills/{skill_name}/{rel_path}"
            fresh = _load_skill_file(skill_name, rel_path)

            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(fresh, encoding="utf-8")
                write_base(root, rel_dest, fresh)
                print(f"  new   {skill_name}/{rel_path}")
                written += 1
                continue

            # Check for uncommitted changes
            result = subprocess.run(
                ["git", "diff", "--quiet", "--", str(dest)], capture_output=True
            )
            if result.returncode != 0:
                print(
                    f"  skip  {skill_name}/{rel_path} (uncommitted changes)",
                )
                continue

            existing = dest.read_text()
            base_text = read_base(root, rel_dest)
            merged, has_conflict = three_way_merge(dest, base_text, fresh)

            if merged.rstrip() == existing.rstrip():
                write_base(root, rel_dest, fresh)
                up_to_date += 1
                continue

            dest.write_text(merged)
            write_base(root, rel_dest, fresh)

            if has_conflict or "<<<<<<" in merged:
                print(f"  merge {skill_name}/{rel_path} (conflicts)")
                editor = resolve_editor(parsed.editor, root)
                if editor:
                    try:
                        answer = input(f"  Open in {editor}? [Y/n] ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        answer = "n"
                    if answer not in ("n", "no"):
                        subprocess.run([*editor_cmd(editor), str(dest)])
                    if "<<<<<<" in dest.read_text():
                        conflicts += 1
                else:
                    conflicts += 1
            else:
                print(f"  merge {skill_name}/{rel_path}")
                written += 1

    _store_skill_version(root)

    print()
    if written:
        print(f"OK: Upgraded {written} file(s) (uvr v{ver})")
    if up_to_date:
        print(f"  {up_to_date} file(s) already up to date.")
    if conflicts:
        print(f"  {conflicts} file(s) have unresolved conflicts.")
