"""The ``uvr workflow init`` and ``uvr workflow init --upgrade`` commands."""

from __future__ import annotations

import argparse
import subprocess
from importlib.resources import files
from pathlib import Path

from ...shared.utils.cli import fatal
from ...shared.utils.toml import get_path, read_pyproject, write_pyproject
from ...shared.utils.yaml import load_yaml
from .._args import CommandArgs
from .._upgrade import (
    editor_cmd,
    read_base,
    resolve_editor,
    three_way_merge,
    write_base,
)


class WorkflowInitArgs(CommandArgs):
    """Typed arguments for ``uvr workflow init``."""

    workflow_dir: str = ".github/workflows"
    force: bool = False
    upgrade: bool = False
    base_only: bool = False
    editor: str | None = None


class WorkflowUpgradeArgs(CommandArgs):
    """Typed arguments for ``uvr workflow init --upgrade``."""

    workflow_dir: str = ".github/workflows"
    editor: str | None = None


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


def _check_frozen_paths(existing: dict, template: dict) -> list[str]:
    """Compare frozen fields between user YAML and bundled template.

    Returns a list of warning messages for each frozen path that differs.
    """
    from ...shared.models.workflow import ReleaseWorkflow, frozen_paths
    from ...shared.utils.yaml import MISSING, yaml_get

    warnings: list[str] = []
    for path in frozen_paths(ReleaseWorkflow):
        keys = path.split(".")
        user_val = yaml_get(existing, keys)
        tmpl_val = yaml_get(template, keys)
        if user_val is MISSING:
            continue  # field absent in user file -- skip
        if tmpl_val is MISSING:
            continue  # field absent in template -- skip
        if user_val != tmpl_val:
            warnings.append(f"{path} was modified from template default")
    return warnings


def _store_workflow_version(root: Path) -> None:
    """Store the current uvr package version as workflow_version in [tool.uvr.config]."""
    from ...shared.utils.cli import __version__

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


def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold the GitHub Actions workflow into your repo."""
    from ...shared.utils.cli import __version__

    parsed = WorkflowInitArgs.from_namespace(args)
    root = Path.cwd()

    if parsed.base_only:
        # --base-only: write merge bases without touching actual files
        rel_dest = f"{parsed.workflow_dir}/release.yml"
        write_base(root, rel_dest, _load_template())
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
    dest_dir = root / parsed.workflow_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "release.yml"

    if dest.exists() and not parsed.force:
        fatal(
            f"{dest.relative_to(root)} already exists.\n"
            "  Use --force to overwrite, or `uvr validate` to check the existing file."
        )

    template_text = _load_template()
    dest.write_text(template_text)

    # Save merge base and store version
    rel_dest = str(dest.relative_to(root))
    write_base(root, rel_dest, template_text)
    _store_workflow_version(root)

    print(f"OK: Wrote workflow to {rel_dest} (uvr v{__version__})")
    print()
    print("Next steps:")
    print("  1. Review and commit the workflow file")
    print("  2. Run `uvr validate` to check your changes")
    print("  3. Trigger a release:")
    print("       uvr release")


def cmd_upgrade(args: argparse.Namespace) -> None:
    """Upgrade an existing release.yml via three-way merge."""
    parsed = WorkflowUpgradeArgs.from_namespace(args)
    root = Path.cwd()
    dest = root / parsed.workflow_dir / "release.yml"

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

    from ...shared.utils.cli import __version__

    rel_dest = str(dest.relative_to(root))
    existing_text = dest.read_text()

    # Read merge base from .uvr/bases/ (empty string -> two-way merge)
    base_text = read_base(root, rel_dest)
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
            uvx_cmd = (
                f"uvx --from uv-release=={stored_version} uvr workflow init --base-only"
            )
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
                    base_text = read_base(root, "release.yml")
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
        print(f"OK: Upgraded {rel_dest} (uvr v{__version__})")
        return

    # Conflicts -- offer editor
    print(f"Upgraded {rel_dest} with conflicts.")
    cli_editor = parsed.editor
    editor = resolve_editor(cli_editor, root)
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
        write_base(root, rel_dest, fresh_text)
        _store_workflow_version(root)
        print(f"  Resolve markers in {rel_dest}, then commit.")
        return

    write_base(root, rel_dest, fresh_text)
    _store_workflow_version(root)
    print(f"OK: Upgraded {rel_dest} (uvr v{__version__})")
