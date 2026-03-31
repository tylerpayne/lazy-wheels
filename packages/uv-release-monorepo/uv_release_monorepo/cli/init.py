"""The ``uvr workflow init``, ``uvr workflow init --upgrade``, and ``uvr validate`` commands."""

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
from ..shared.utils.toml import get_path, read_pyproject, write_pyproject
from ..shared.utils.cli import fatal
from ..shared.utils.yaml import MISSING, load_yaml, yaml_get


_FALLBACK_EDITORS = ("code", "vim", "vi", "nano")

# Editors that launch a GUI and return immediately — need --wait to block
_WAIT_EDITORS = {"code", "codium", "subl", "atom", "zed"}


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

_TEMPLATE_PATH = files("uv_release_monorepo").joinpath("templates/release/release.yml")


def _load_template() -> str:
    """Load the bundled release workflow template."""
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def _load_template_yaml() -> dict:
    """Load and parse the bundled template as a dict."""
    import tempfile as _tmp

    text = _load_template()
    with _tmp.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(text)
        tmp = Path(f.name)
    try:
        return load_yaml(tmp)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# .uvr/bases/ — local merge base storage
# ---------------------------------------------------------------------------

_UVR_DIR = ".uvr"
_BASES_DIR = f"{_UVR_DIR}/bases"


def _write_base(root: Path, rel_path: str, content: str) -> None:
    """Save a merge base to .uvr/bases/<rel_path>."""
    base_file = root / _BASES_DIR / rel_path
    base_file.parent.mkdir(parents=True, exist_ok=True)
    base_file.write_text(content)


def _read_base(root: Path, rel_path: str) -> str:
    """Read a merge base from .uvr/bases/<rel_path>, or empty string if absent."""
    base_file = root / _BASES_DIR / rel_path
    if base_file.exists():
        return base_file.read_text()
    return ""


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
        user_val = yaml_get(existing, keys)
        tmpl_val = yaml_get(template, keys)
        if user_val is MISSING:
            continue  # field absent in user file — skip
        if tmpl_val is MISSING:
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


def _store_workflow_version(root: Path) -> None:
    """Store the current uvr package version as workflow_version in [tool.uvr.config]."""
    from ..shared.utils.cli import __version__

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return
    doc = read_pyproject(pyproject)
    tool = doc.setdefault("tool", {})
    uvr = tool.setdefault("uvr", {})
    config = uvr.setdefault("config", {})
    config["workflow_version"] = __version__
    # Remove legacy keys if present
    config.pop("init_commit", None)
    write_pyproject(pyproject, doc)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_init_dispatch(args: argparse.Namespace) -> None:
    """Route to cmd_init or cmd_upgrade based on --upgrade flag."""
    if getattr(args, "upgrade", False):
        cmd_upgrade(args)
    else:
        cmd_init(args)


def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold the GitHub Actions workflow into your repo."""
    from ..shared.utils.cli import __version__

    root = Path.cwd()
    base_only = getattr(args, "base_only", False)

    if base_only:
        # --base-only: write merge bases without touching actual files
        workflow_dir = getattr(args, "workflow_dir", ".github/workflows")
        rel_dest = f"{workflow_dir}/release.yml"
        _write_base(root, rel_dest, _load_template())
        print(f"OK: Wrote merge base for {rel_dest} (uvr v{__version__})")
        return

    # Sanity checks
    if not (root / ".git").exists():
        fatal("Not a git repository. Run from the repo root.")

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        fatal("No pyproject.toml found in current directory.")

    doc = read_pyproject(pyproject)
    members = doc.get("tool", {}).get("uv", {}).get("workspace", {}).get("members")
    if not members:
        fatal(
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
        fatal(
            f"{dest.relative_to(root)} already exists.\n"
            "  Use --force to overwrite, or `uvr validate` to check the existing file."
        )

    template_text = _load_template()
    dest.write_text(template_text)

    # Save merge base and store version
    rel_dest = str(dest.relative_to(root))
    _write_base(root, rel_dest, template_text)
    _store_workflow_version(root)

    print(f"OK: Wrote workflow to {rel_dest} (uvr v{__version__})")
    print()
    print("Next steps:")
    print("  1. Review and commit the workflow file")
    print("  2. Run `uvr validate` to check your changes")
    print("  3. Trigger a release:")
    print("       uvr release")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate an existing release.yml against the ReleaseWorkflow model."""
    root = Path.cwd()
    workflow_dir = getattr(args, "workflow_dir", ".github/workflows")
    dest = root / workflow_dir / "release.yml"

    if not dest.exists():
        fatal(
            f"No workflow found at {dest.relative_to(root)}. Run `uvr workflow init` first."
        )

    import difflib
    import warnings

    from pydantic import ValidationError

    existing = load_yaml(dest)
    rel = dest.relative_to(root)

    from ..shared.utils.cli import __version__

    # Resolve versions
    stored_version = ""
    if (root / "pyproject.toml").exists():
        stored_version = get_path(
            read_pyproject(root / "pyproject.toml"),
            "tool",
            "uvr",
            "config",
            "workflow_version",
            default="",
        )
    local_label = f"v{stored_version}" if stored_version else "unknown"

    # Header
    print(
        f"Validating worktree workflow {rel} ({local_label}) "
        f"against uvr template (v{__version__})."
    )
    print()

    # Phase 1: Structural validation via pydantic
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            ReleaseWorkflow.model_validate(existing)
        except ValidationError as e:
            print(f"FAIL: {e}")
            raise SystemExit(1) from None

    # Phase 2: Frozen-path diffing against bundled template
    template = _load_template_yaml()
    frozen_warnings = _check_frozen_paths(existing, template)
    all_warnings = [str(w.message) for w in caught] + frozen_warnings

    # Check if template content differs
    fresh_text = _load_template()
    existing_text = dest.read_text()
    has_diff = fresh_text.rstrip() != existing_text.rstrip()
    version_diff = stored_version and stored_version != __version__

    # Result
    if all_warnings:
        print(f"SUCCESS: 0 errors, {len(all_warnings)} warnings")
        print()
        print("Warnings:")
        for w in all_warnings:
            print(f"  {w}")
    else:
        print("SUCCESS: 0 errors, 0 warnings")

    # Hints
    if has_diff:
        print()
        print("  Run `uvr validate --diff` to view differences from the template.")
    if version_diff:
        print(
            f"  Run `uvr workflow init --upgrade` to update from "
            f"v{stored_version} to v{__version__}."
        )
    elif not stored_version:
        print("  Run `uvr workflow init --upgrade` to track your workflow version.")

    # --diff: show unified diff
    if getattr(args, "diff", False) and has_diff:
        print()
        diff = difflib.unified_diff(
            existing_text.splitlines(keepends=True),
            fresh_text.splitlines(keepends=True),
            fromfile=str(rel),
            tofile=f"template (v{__version__})",
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
        fatal(f"git merge-file failed:\n{result.stderr}")

    return result.stdout, result.returncode > 0


def cmd_upgrade(args: argparse.Namespace) -> None:
    """Upgrade an existing release.yml via three-way merge."""
    root = Path.cwd()
    workflow_dir = getattr(args, "workflow_dir", ".github/workflows")
    dest = root / workflow_dir / "release.yml"

    if not dest.exists():
        fatal(
            f"No workflow found at {dest.relative_to(root)}. Run `uvr workflow init` first."
        )

    # Ensure release.yml has no uncommitted changes
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", str(dest)],
        capture_output=True,
    )
    if result.returncode != 0:
        fatal(
            f"{dest.relative_to(root)} has uncommitted changes.\n"
            "  Commit or stash them before upgrading."
        )

    from ..shared.utils.cli import __version__

    rel_dest = str(dest.relative_to(root))
    existing_text = dest.read_text()

    # Read merge base from .uvr/bases/ (empty string → two-way merge)
    base_text = _read_base(root, rel_dest)
    if not base_text:
        stored_version = ""
        if (root / "pyproject.toml").exists():
            stored_version = get_path(
                read_pyproject(root / "pyproject.toml"),
                "tool",
                "uvr",
                "config",
                "workflow_version",
                default="",
            )
        if stored_version:
            uvx_cmd = f"uvx --from uv-release-monorepo=={stored_version} uvr workflow init --base-only"
            print(
                f"No merge base found. For a cleaner upgrade, recover the base first:\n"
                f"  {uvx_cmd}\n"
                f"  uvr workflow init --upgrade\n"
            )
            try:
                run_it = input("Run the uvx command above? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                run_it = ""
            if run_it == "y":
                result = subprocess.run(uvx_cmd, shell=True)
                if result.returncode == 0:
                    # Re-check for merge base after recovery
                    base_text = _read_base(root, "release.yml")
                    if base_text:
                        print("Base recovered. Proceeding with three-way merge.")
            else:
                try:
                    answer = (
                        input("Continue with two-way merge? [y/N] ").strip().lower()
                    )
                except (EOFError, KeyboardInterrupt):
                    answer = ""
                if answer != "y":
                    return
    fresh_text = _load_template()

    merged_text, has_conflicts = _three_way_merge(dest, base_text, fresh_text)

    if merged_text.rstrip() == existing_text.rstrip():
        _write_base(root, rel_dest, fresh_text)
        _store_workflow_version(root)
        print("Already up to date.")
        return

    dest.write_text(merged_text)

    if not (has_conflicts or "<<<<<<" in merged_text):
        _write_base(root, rel_dest, fresh_text)
        _store_workflow_version(root)
        print(f"OK: Upgraded {rel_dest} (uvr v{__version__})")
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
            return
        _write_base(root, rel_dest, fresh_text)
        _store_workflow_version(root)
        print(f"  Resolve markers in {rel_dest}, then commit.")
        return

    _write_base(root, rel_dest, fresh_text)
    _store_workflow_version(root)
    print(f"OK: Upgraded {rel_dest} (uvr v{__version__})")
