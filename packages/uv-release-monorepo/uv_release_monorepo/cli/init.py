"""The ``uvr init``, ``uvr init --upgrade``, and ``uvr validate`` commands."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

import shutil

from ..shared.config import get_config
from ..shared.models.workflow import ReleaseWorkflow
from ..shared.toml import read_pyproject, write_pyproject
from ._common import _fatal
from ._yaml import _dump_yaml, _load_yaml, _write_yaml


_FALLBACK_EDITORS = ("code", "vim", "vi", "nano")

# Editors that launch a GUI and return immediately — need --wait to block
_WAIT_EDITORS = {"code", "codium", "subl", "atom", "zed"}


def _editor_cmd(editor: str) -> list[str]:
    """Build the editor command, adding --wait for GUI editors that need it."""
    base = Path(editor).stem
    if base in _WAIT_EDITORS:
        return [editor, "--wait"]
    return [editor]


def _resolve_editor(args: argparse.Namespace, root: Path) -> str | None:
    """Resolve editor: --editor CLI arg > [tool.uvr.config].editor > $VISUAL > $EDITOR > fallback."""
    # CLI arg
    cli_editor = getattr(args, "editor", None)
    if cli_editor:
        return cli_editor

    # [tool.uvr.config].editor
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        config = get_config(read_pyproject(pyproject))
        toml_editor = config.get("editor", "")
        if toml_editor:
            return toml_editor

    # Environment variables
    env_editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if env_editor:
        return env_editor

    # Fallback: first available from known editors
    for name in _FALLBACK_EDITORS:
        if shutil.which(name):
            return name

    return None


def _git_commit_and_record(
    root: Path,
    files: list[str],
    message: str,
    config_key: str,
) -> None:
    """Stage *files*, commit, and store the commit hash in [tool.uvr.config].

    Prompts the user for confirmation before committing.
    """
    from ..shared.git.local import open_repo

    rel_files = [str(Path(f).relative_to(root)) for f in files]
    print()
    print("The following will be committed:")
    for f in rel_files:
        print(f"  git add {f}")
    print(f'  git commit -m "{message}"')
    print()
    try:
        answer = input("Commit? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nSkipped commit.")
        return
    if answer and answer != "y":
        print("Skipped commit.")
        return

    repo = open_repo(str(root))
    for f in rel_files:
        repo.index.add(f)
    repo.index.write()

    sig = repo.default_signature
    tree = repo.index.write_tree()
    parent = repo.head.peel().id
    commit_oid = repo.create_commit("HEAD", sig, sig, message, tree, [parent])

    # Store the commit hash in [tool.uvr.config]
    pyproject = root / "pyproject.toml"
    doc = read_pyproject(pyproject)
    tool = doc.setdefault("tool", {})
    uvr = tool.setdefault("uvr", {})
    config = uvr.setdefault("config", {})
    config[config_key] = str(commit_oid)
    write_pyproject(pyproject, doc)

    # Amend the commit to include the pyproject.toml change
    repo.index.add("pyproject.toml")
    repo.index.write()
    tree = repo.index.write_tree()
    repo.create_commit("HEAD", sig, sig, message, tree, [parent])

    print(f"OK: Committed {len(rel_files)} file(s)")


def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold the GitHub Actions workflow into your repo."""
    root = Path.cwd()

    # Sanity checks
    if not (root / ".git").exists():
        _fatal("Not a git repository. Run from the repo root.")

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        _fatal("No pyproject.toml found in current directory.")

    doc = read_pyproject(pyproject)
    members = doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members")
    if not members:
        _fatal(
            "No [tool.uv.workspace] members defined in pyproject.toml.\n"
            "uvr requires a uv workspace. Example:\n\n"
            "  [tool.uv.workspace]\n"
            '  members = ["packages/*"]'
        )

    # Write workflow
    dest_dir = root / args.workflow_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "release.yml"

    force = getattr(args, "force", False)
    if dest.exists() and not force:
        _fatal(
            f"{dest.relative_to(root)} already exists.\n"
            "  Use --force to overwrite, or `uvr validate` to check the existing file."
        )

    _write_yaml(dest, ReleaseWorkflow().model_dump(by_alias=True, exclude_none=True))

    print(f"OK: Wrote workflow to {dest.relative_to(root)}")

    _git_commit_and_record(
        root,
        [str(dest)],
        "chore: uvr init",
        "init_commit",
    )

    print()
    print("Next steps:")
    print("  1. Edit the workflow to add your hook steps")
    print("  2. Run `uvr validate` to check your changes")
    print("  3. Commit and push the workflow file")
    print("  4. Trigger a release:")
    print("       uvr release")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate an existing release.yml against the ReleaseWorkflow model."""
    root = Path.cwd()
    workflow_dir = getattr(args, "workflow_dir", ".github/workflows")
    dest = root / workflow_dir / "release.yml"

    if not dest.exists():
        _fatal(f"No workflow found at {dest.relative_to(root)}. Run `uvr init` first.")

    import warnings

    from pydantic import ValidationError

    existing = _load_yaml(dest)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            ReleaseWorkflow.model_validate(existing)
        except ValidationError as e:
            print(f"Invalid: {dest.relative_to(root)}\n{e}")
            raise SystemExit(1) from None

    rel = dest.relative_to(root)
    if caught:
        print(f"Valid: {rel} (0 errors, {len(caught)} warnings)\n")
        print("Warnings:")
        for w in caught:
            print(f"  {w.message}")
    else:
        print(f"Valid: {rel} (0 errors, 0 warnings)")


def _get_base_text(root: Path, rel_path: str, config_key: str) -> str:
    """Retrieve the base file content from the init commit, or empty string."""
    import pygit2

    from ..shared.git.local import open_repo

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return ""
    doc = read_pyproject(pyproject)
    commit_hex = doc.get("tool", {}).get("uvr", {}).get("config", {}).get(config_key)
    if not commit_hex:
        return ""

    try:
        repo = open_repo(str(root))
        commit = repo.get(commit_hex)
        if commit is None:
            return ""
        tree = commit.peel(pygit2.Tree) if hasattr(commit, "peel") else commit.tree
        entry = tree[rel_path]
        blob = repo.get(entry.id)
        if blob is None:
            return ""
        return blob.data.decode("utf-8")  # type: ignore[union-attr]
    except (KeyError, ValueError, AttributeError):
        return ""


def _three_way_merge(dest: Path, base_text: str, fresh_text: str) -> tuple[str, bool]:
    """Run git merge-file and return (merged_text, has_conflicts)."""
    with (
        tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", prefix="base-", delete=False
        ) as base_f,
        tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", prefix="fresh-", delete=False
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
                "template",
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
        _fatal(f"git merge-file failed:\n{result.stderr}")

    return result.stdout, result.returncode > 0


def cmd_upgrade(args: argparse.Namespace) -> None:
    """Upgrade an existing release.yml via three-way merge (falling back to two-way)."""
    root = Path.cwd()
    workflow_dir = getattr(args, "workflow_dir", ".github/workflows")
    dest = root / workflow_dir / "release.yml"

    if not dest.exists():
        _fatal(f"No workflow found at {dest.relative_to(root)}. Run `uvr init` first.")

    # Ensure release.yml has no uncommitted changes
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", str(dest)],
        capture_output=True,
    )
    if result.returncode != 0:
        _fatal(
            f"{dest.relative_to(root)} has uncommitted changes.\n"
            "  Commit or stash them before upgrading."
        )

    existing_text = dest.read_text()
    rel_dest = str(dest.relative_to(root))

    fresh_text = _dump_yaml(
        ReleaseWorkflow().model_dump(by_alias=True, exclude_none=True)
    )
    base_text = _get_base_text(root, rel_dest, "init_commit")
    merged_text, has_conflicts = _three_way_merge(dest, base_text, fresh_text)

    if merged_text.rstrip() == existing_text.rstrip():
        print("Already up to date.")
        return

    dest.write_text(merged_text)

    if not (has_conflicts or "<<<<<<" in merged_text):
        print(f"OK: Upgraded {rel_dest}")
        _git_commit_and_record(
            root, [str(dest)], "chore: uvr init --upgrade", "init_commit"
        )
        return

    # Conflicts — offer editor
    print(f"Upgraded {rel_dest} with conflicts.")
    editor = _resolve_editor(args, root)
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
            subprocess.run([*_editor_cmd(chosen), str(dest)])
    elif editor and answer == "":
        subprocess.run([*_editor_cmd(editor), str(dest)])

    # Check if conflicts were resolved
    if "<<<<<<" in dest.read_text():
        print("Unresolved conflicts remain.")
        try:
            answer = input("Revert to original? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("n", "no"):
            dest.write_text(existing_text)
            print("Reverted. No changes applied.")
        else:
            print(f"  Resolve markers in {rel_dest}, then commit.")
