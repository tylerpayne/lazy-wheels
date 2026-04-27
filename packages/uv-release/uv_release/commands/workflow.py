"""Commands for CI dispatch and file upgrade merges."""

from __future__ import annotations

from typing import Literal

from ..types import Command


class DispatchWorkflowCommand(Command):
    """Dispatch a release plan to GitHub Actions."""

    type: Literal["dispatch_workflow"] = "dispatch_workflow"
    plan_json: str
    workflow: str = "release.yml"

    def execute(self) -> int:
        import subprocess

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
        )
        ref = result.stdout.strip() if result.returncode == 0 else "main"

        return subprocess.run(
            [
                "gh",
                "workflow",
                "run",
                self.workflow,
                "--ref",
                ref,
                "-f",
                f"plan={self.plan_json}",
            ],
        ).returncode


class MergeUpgradeCommand(Command):
    """Three-way merge of a file with interactive conflict resolution.

    Reads the current file, merges with base and fresh versions, writes the result.
    If conflicts remain, opens an editor and offers to revert.
    """

    type: Literal["merge_upgrade"] = "merge_upgrade"
    dest_path: str
    base_text: str
    fresh_text: str
    editor: str = ""

    def execute(self) -> int:
        import subprocess
        from pathlib import Path

        from ..utils.merge import merge_texts, parse_editor_command

        dest = Path(self.dest_path)
        existing_text = dest.read_text()

        merged_text, has_conflicts = merge_texts(
            existing_text, self.base_text, self.fresh_text
        )

        if merged_text.rstrip() == existing_text.rstrip():
            print(f"  {self.dest_path}: already up to date")
            return 0

        dest.write_text(merged_text)

        if not (has_conflicts or "<<<<<<" in merged_text):
            print(f"  {self.dest_path}: merged cleanly")
            return 0

        # Conflicts: interactive resolution
        print(f"  {self.dest_path}: merged with conflicts")
        if self.editor:
            prompt = f"  Open in {self.editor} to resolve? [Y/n] "
        else:
            prompt = "  Resolve conflicts manually, then press Enter. [n to skip] "

        try:
            answer = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        if self.editor and answer not in ("n", "no"):
            subprocess.run([*parse_editor_command(self.editor), str(dest)])

        if "<<<<<<" in dest.read_text():
            print("  Unresolved conflicts remain.")
            try:
                revert = input("  Revert to original? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                revert = ""
            if revert not in ("n", "no"):
                dest.write_text(existing_text)
                print("  Reverted.")
                return 1

        return 0
