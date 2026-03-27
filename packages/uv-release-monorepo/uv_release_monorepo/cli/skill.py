"""The ``uvr skill init`` command."""

from __future__ import annotations

import argparse
from importlib.resources import files
from pathlib import Path

from ._common import _fatal

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
    """Return the root of the bundled skills directory as a concrete Path.

    ``importlib.resources.files`` returns a ``Traversable`` that, for
    filesystem-installed packages, is already a ``Path``.  We cast here so
    callers can use normal ``Path`` operations.
    """
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
        print(f"\u2713 Wrote {written} file(s) to .claude/skills/")
    if skipped:
        print(f"  Skipped {skipped} existing file(s). Use --force to overwrite.")
    if not written and not skipped:
        print("Nothing to do.")

    if written:
        print()
        print("Next steps:")
        print("  1. Review .claude/skills/release/SKILL.md and tailor to your project")
        print("  2. Commit the skill files to your repo")
        print("  3. Use /release in Claude Code to start a release")
