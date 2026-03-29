"""The ``uvr init``, ``uvr init --upgrade``, and ``uvr validate`` commands."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from ..shared.models.workflow import ReleaseWorkflow, frozen_paths
from ..shared.utils.config import get_config
from ..shared.utils.toml import read_pyproject, write_pyproject
from ._common import _fatal
from ._yaml import _MISSING, _load_yaml, _yaml_get


_FALLBACK_EDITORS = ("code", "vim", "vi", "nano")

# Editors that launch a GUI and return immediately — need --wait to block
_WAIT_EDITORS = {"code", "codium", "subl", "atom", "zed"}


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = files("uv_release_monorepo").joinpath("templates/release")


def _template_versions() -> list[str]:
    """Return sorted list of available template versions (e.g. ['0.18.0'])."""
    from packaging.version import Version

    versions: list[str] = []
    for item in _TEMPLATE_DIR.iterdir():
        name = item.name if hasattr(item, "name") else str(item).rsplit("/", 1)[-1]
        if name.startswith("v") and name.endswith(".yml"):
            versions.append(name[1:-4])  # strip v prefix and .yml suffix
    return sorted(versions, key=Version)


def _latest_template_version() -> str:
    """Return the latest bundled template version string."""
    versions = _template_versions()
    if not versions:
        _fatal("No bundled release templates found.")
    return versions[-1]


def _load_template(version: str) -> str:
    """Load a bundled template by version string (e.g. '0.18.0')."""
    resource = _TEMPLATE_DIR.joinpath(f"v{version}.yml")
    return resource.read_text(encoding="utf-8")


def _load_template_yaml(version: str) -> dict:
    """Load and parse a bundled template as a dict."""
    import tempfile as _tmp

    text = _load_template(version)
    with _tmp.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(text)
        tmp = Path(f.name)
    try:
        return _load_yaml(tmp)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Frozen-path validation
# ---------------------------------------------------------------------------


def _check_frozen_paths(existing: dict, template: dict) -> list[str]:
    """Compare frozen fields between user YAML and bundled template.

    Returns a list of warning messages for each frozen path that differs.
    """
    warnings: list[str] = []
    for path in frozen_paths(ReleaseWorkflow):
        keys = path.split(".")
        user_val = _yaml_get(existing, keys)
        tmpl_val = _yaml_get(template, keys)
        if user_val is _MISSING:
            continue  # field absent in user file — skip
        if tmpl_val is _MISSING:
            continue  # field absent in template — skip
        if user_val != tmpl_val:
            warnings.append(f"{path} was modified from template default")
    return warnings


# ---------------------------------------------------------------------------
# Editor helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_commit_and_record(
    root: Path,
    files_to_commit: list[str],
    message: str,
    *,
    template_version: str | None = None,
) -> None:
    """Stage *files*, commit, and store the template version in [tool.uvr.config].

    Prompts the user for confirmation before committing.
    """
    from ..shared.git.local import open_repo

    rel_files = [str(Path(f).relative_to(root)) for f in files_to_commit]
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
    repo.create_commit("HEAD", sig, sig, message, tree, [parent])

    # Store the template version in [tool.uvr.config]
    if template_version:
        pyproject = root / "pyproject.toml"
        doc = read_pyproject(pyproject)
        tool = doc.setdefault("tool", {})
        uvr = tool.setdefault("uvr", {})
        config = uvr.setdefault("config", {})
        config["template_version"] = template_version
        # Remove legacy init_commit if present
        config.pop("init_commit", None)
        write_pyproject(pyproject, doc)

        # Amend the commit to include the pyproject.toml change
        repo.index.add("pyproject.toml")
        repo.index.write()
        tree = repo.index.write_tree()
        repo.create_commit("HEAD", sig, sig, message, tree, [repo.head.peel().id])

    print(f"OK: Committed {len(rel_files)} file(s)")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


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

    # Write workflow from bundled template
    dest_dir = root / args.workflow_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "release.yml"

    force = getattr(args, "force", False)
    if dest.exists() and not force:
        _fatal(
            f"{dest.relative_to(root)} already exists.\n"
            "  Use --force to overwrite, or `uvr validate` to check the existing file."
        )

    version = _latest_template_version()
    dest.write_text(_load_template(version))

    print(f"OK: Wrote workflow to {dest.relative_to(root)}")

    _git_commit_and_record(
        root,
        [str(dest)],
        "chore: uvr init",
        template_version=version,
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

    import difflib
    import warnings

    from pydantic import ValidationError

    from ._common import __version__

    existing = _load_yaml(dest)
    rel = dest.relative_to(root)

    # Phase 1: Structural validation via pydantic
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            ReleaseWorkflow.model_validate(existing)
        except ValidationError as e:
            print(f"FAIL: {rel}\n{e}")
            raise SystemExit(1) from None

    # Phase 2: Frozen-path diffing against bundled template
    template_version = _latest_template_version()
    template = _load_template_yaml(template_version)
    frozen_warnings = _check_frozen_paths(existing, template)

    all_warnings = [str(w.message) for w in caught] + frozen_warnings

    # Check if template content differs from current file
    fresh_text = _load_template(template_version)
    existing_text = dest.read_text()
    has_diff = fresh_text.rstrip() != existing_text.rstrip()

    # Status line first
    if all_warnings:
        print(f"SUCCESS: {rel} (0 errors, {len(all_warnings)} warnings)")
    else:
        print(f"SUCCESS: {rel} (0 errors, 0 warnings)")
    print()

    # Version info
    uvr_version = __version__
    stored_version = (root / "pyproject.toml").exists() and get_config(
        read_pyproject(root / "pyproject.toml")
    ).get("template_version", "")
    print(f"  uvr version:       {uvr_version}")
    print(f"  template version:  {template_version}")
    if stored_version:
        print(f"  installed version: {stored_version}")
    else:
        print("  installed version: (unknown — run `uvr init --upgrade` to set)")

    # Warnings
    if all_warnings:
        print()
        print("Warnings:")
        for w in all_warnings:
            print(f"  {w}")

    if has_diff:
        print()
        if stored_version and stored_version != template_version:
            print(
                f"  Template updated: {stored_version} → {template_version}. "
                "Run `uvr init --upgrade` to apply."
            )
        else:
            print("  Run `uvr validate --diff` to view differences from the template.")
            print("  Run `uvr init --upgrade` to update from the template.")

    # --diff: show unified diff
    if getattr(args, "diff", False) and has_diff:
        print()
        diff = difflib.unified_diff(
            existing_text.splitlines(keepends=True),
            fresh_text.splitlines(keepends=True),
            fromfile=str(rel),
            tofile=f"template (v{template_version})",
        )
        for line in diff:
            print(line, end="")


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
    """Upgrade an existing release.yml via three-way merge."""
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

    # Resolve base template version from config
    pyproject = root / "pyproject.toml"
    doc = read_pyproject(pyproject) if pyproject.exists() else {}
    stored_version = (
        doc.get("tool", {}).get("uvr", {}).get("config", {}).get("template_version")
    )
    if not stored_version:
        _fatal(
            "No template_version found in [tool.uvr.config].\n"
            "  Run `uvr init --force` to re-initialize."
        )

    latest_version = _latest_template_version()
    existing_text = dest.read_text()

    base_text = _load_template(stored_version)
    fresh_text = _load_template(latest_version)

    merged_text, has_conflicts = _three_way_merge(dest, base_text, fresh_text)

    if merged_text.rstrip() == existing_text.rstrip():
        print("Already up to date.")
        return

    rel_dest = str(dest.relative_to(root))
    dest.write_text(merged_text)

    if not (has_conflicts or "<<<<<<" in merged_text):
        print(f"OK: Upgraded {rel_dest}")
        _git_commit_and_record(
            root,
            [str(dest)],
            "chore: uvr init --upgrade",
            template_version=latest_version,
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
