"""The ``uvr workflow init`` and ``uvr workflow init --upgrade`` commands."""

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

_TEMPLATE_PATH = files("uv_release").joinpath("templates/release/release.yml")


class WorkflowInitArgs(CommandArgs):
    """Typed arguments for ``uvr workflow init``."""

    workflow_dir: str = ".github/workflows"
    force: bool = False
    upgrade: bool = False
    base_only: bool = False
    editor: str | None = None


def _load_template() -> str:
    """Load the bundled release workflow template."""
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def _store_workflow_version(root: Path) -> None:
    """Store the current uvr version as workflow_version in [tool.uvr.config]."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return
    doc = tomlkit.loads(pyproject.read_text())
    tool = doc.setdefault("tool", {})
    uvr = tool.setdefault("uvr", {})
    config = uvr.setdefault("config", {})
    config["workflow_version"] = _uvr_version()
    pyproject.write_text(tomlkit.dumps(doc))


def _uvr_version() -> str:
    from importlib.metadata import version

    return version("uv_release")


def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold the GitHub Actions workflow into your repo."""
    parsed = WorkflowInitArgs.from_namespace(args)
    root = Path.cwd()
    ver = _uvr_version()

    if parsed.base_only:
        rel_dest = f"{parsed.workflow_dir}/release.yml"
        write_base(root, rel_dest, _load_template())
        print(f"OK: Wrote merge base for {rel_dest} (uvr v{ver})")
        return

    if not (root / ".git").exists():
        print("ERROR: Not a git repository. Run from the repo root.", file=sys.stderr)
        sys.exit(1)

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        print("ERROR: No pyproject.toml found.", file=sys.stderr)
        sys.exit(1)

    doc = tomlkit.loads(pyproject.read_text())
    members = doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members")
    if not members:
        print(
            "ERROR: No [tool.uv.workspace] members in pyproject.toml.",
            file=sys.stderr,
        )
        sys.exit(1)

    dest_dir = root / parsed.workflow_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "release.yml"

    if dest.exists() and not parsed.force:
        print(
            f"ERROR: {dest.relative_to(root)} already exists. "
            f"Use --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)

    template_text = _load_template()
    dest.write_text(template_text)

    rel_dest = str(dest.relative_to(root))
    write_base(root, rel_dest, template_text)
    _store_workflow_version(root)

    print(f"OK: Wrote workflow to {rel_dest} (uvr v{ver})")
    print()
    print("Next steps:")
    print("  1. Review and commit the workflow file")
    print("  2. Run `uvr workflow validate` to check your changes")
    print("  3. Trigger a release with `uvr release`")


def cmd_upgrade(args: argparse.Namespace) -> None:
    """Upgrade an existing release.yml via three-way merge."""
    parsed = WorkflowInitArgs.from_namespace(args)
    root = Path.cwd()
    dest = root / parsed.workflow_dir / "release.yml"

    if not dest.exists():
        print(
            f"ERROR: No workflow found at {dest.relative_to(root)}. "
            f"Run `uvr workflow init` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    result = subprocess.run(
        ["git", "diff", "--quiet", "--", str(dest)], capture_output=True
    )
    if result.returncode != 0:
        print(
            f"ERROR: {dest.relative_to(root)} has uncommitted changes. "
            f"Commit or stash them first.",
            file=sys.stderr,
        )
        sys.exit(1)

    ver = _uvr_version()
    rel_dest = str(dest.relative_to(root))
    existing_text = dest.read_text()
    base_text = read_base(root, rel_dest)
    fresh_text = _load_template()

    merged_text, has_conflicts = three_way_merge(dest, base_text, fresh_text)

    if merged_text.rstrip() == existing_text.rstrip():
        write_base(root, rel_dest, fresh_text)
        _store_workflow_version(root)
        print("Already up to date.")
        return

    dest.write_text(merged_text)

    if not (has_conflicts or "<<<<<<" in merged_text):
        write_base(root, rel_dest, fresh_text)
        _store_workflow_version(root)
        print(f"OK: Upgraded {rel_dest} (uvr v{ver})")
        return

    # Conflicts
    print(f"Upgraded {rel_dest} with conflicts.")
    editor = resolve_editor(parsed.editor, root)
    prompt = (
        f"Open in {editor} to resolve? [Y/n/editor] "
        if editor
        else "Editor to resolve? [n/editor] "
    )
    try:
        answer = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    if answer.lower() not in ("n", "no", ""):
        chosen = editor if answer.lower() in ("y", "yes") else answer
        if chosen:
            subprocess.run([*editor_cmd(chosen), str(dest)])
    elif editor and answer == "":
        subprocess.run([*editor_cmd(editor), str(dest)])

    if "<<<<<<" in dest.read_text():
        print("Unresolved conflicts remain.")
        try:
            answer = input("Revert to original? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("n", "no"):
            dest.write_text(existing_text)
            print("Reverted. No changes applied.")
            return
        write_base(root, rel_dest, fresh_text)
        _store_workflow_version(root)
        print(f"  Resolve markers in {rel_dest}, then commit.")
        return

    write_base(root, rel_dest, fresh_text)
    _store_workflow_version(root)
    print(f"OK: Upgraded {rel_dest} (uvr v{ver})")
