"""Fetch template content from a specific uv-release version via uvx.

Used by `uvr workflow install --upgrade` and `uvr skill install --upgrade` to
populate `.uvr/bases/` with the template content from the user's last-accepted
uv-release version. The bases folder is treated as a transient cache. The
authoritative record of "what version did the user last accept" lives in
[tool.uvr.config].workflow-version / skill-version in pyproject.toml.

Each fetch has two paths:

1. Primary: `uvx --from uv-release=={version} uvr ... install --print-template`.
   Fast and uses the version's own template-emission code.
2. Fallback: `uv pip install --target <tmp> uv-release=={version}` and read
   the template files directly from `uv_release/templates/...`. This rescues
   older releases where `--print-template` short-circuits *after* DI resolves
   the install job — that resolution raises "already exists" whenever the
   caller's cwd already has the file, breaking the primary path. The fallback
   bypasses the CLI entirely and only relies on the bundled file layout, which
   has been stable since the templates landed.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from ..ui.console import console
from .base import Command

# Internal contract with older releases: templates have lived at these paths
# inside the wheel since the feature was introduced. If they ever move, the
# fallback for prior versions stops working — but the primary path keeps
# working for the version after the move, since the bug is fixed upstream.
_WORKFLOW_TEMPLATE_REL = Path("uv_release") / "templates" / "release" / "release.yml"
_SKILLS_TEMPLATE_REL = Path("uv_release") / "templates" / "skills"


class FetchWorkflowBaseCommand(Command):
    """Fetch the workflow template from a specific uv-release version.

    Tries `uvx ... --print-template` first; on failure, installs the package
    into a temp directory and reads the template file directly.
    """

    type: Literal["fetch_workflow_base"] = "fetch_workflow_base"
    from_version: str
    output_path: str

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        content = _fetch_via_uvx(
            self.from_version, ["workflow", "install", "--print-template"]
        )
        if content is None:
            # uvx failed: try the install-and-read fallback.
            content = _read_workflow_from_install(self.from_version)
            if content is None:
                return 1
        out = Path(self.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        return 0


class FetchSkillBasesCommand(Command):
    """Fetch every bundled skill template from a specific uv-release version.

    Tries `uvx ... --print-template` first; on failure (or when the payload
    is unparseable), installs the package into a temp directory and reads
    each template file directly from `uv_release/templates/skills/`.
    """

    type: Literal["fetch_skill_bases"] = "fetch_skill_bases"
    from_version: str
    output_root: str

    def execute(self) -> int:
        if self.label:
            console.print(f"  {self.label}")
        payload_json = _fetch_via_uvx(
            self.from_version, ["skill", "install", "--print-template"]
        )
        files_by_skill: dict[str, list[tuple[str, str]]] | None = None
        if payload_json is not None:
            files_by_skill = _parse_skill_payload(payload_json)
        if files_by_skill is None:
            # uvx failed or returned junk: fall back to install-and-read.
            files_by_skill = _read_skills_from_install(self.from_version)
            if files_by_skill is None:
                return 1
        root = Path(self.output_root)
        for skill_name, entries in files_by_skill.items():
            for rel, content in entries:
                target = root / skill_name / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        return 0


def _fetch_via_uvx(from_version: str, sub_argv: list[str]) -> str | None:
    """Run `uvx --from uv-release==X uvr <sub_argv>` and return stdout.

    Returns None on non-zero exit so the caller can fall back. Prints a short
    diagnostic so the user sees why the primary path was skipped.
    """
    result = subprocess.run(
        ["uvx", "--from", f"uv-release=={from_version}", "uvr", *sub_argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        # Truncate stderr so a multi-line failure (uv install output + inner
        # uvr error) doesn't dominate the user's terminal.
        stderr = result.stderr.strip().splitlines()
        tail = stderr[-1] if stderr else ""
        console.print(f"    uvx fetch for uv-release {from_version} failed: {tail}")
        return None
    return result.stdout


def _parse_skill_payload(payload_json: str) -> dict[str, list[tuple[str, str]]] | None:
    """Parse the JSON map emitted by `uvr skill install --print-template`.

    Returns None on parse failure (caller falls back). Empty entries with no
    rel_path are dropped silently.
    """
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        console.print(f"    Could not parse skill template payload: {exc}")
        return None
    out: dict[str, list[tuple[str, str]]] = {}
    for skill_name, files in payload.items():
        entries: list[tuple[str, str]] = []
        for entry in files:
            rel = entry.get("rel_path", "")
            content = entry.get("content", "")
            if rel:
                entries.append((rel, content))
        if entries:
            out[skill_name] = entries
    return out


def _install_uv_release(from_version: str, target: Path) -> bool:
    """Install uv-release=={version} into target dir with no deps.

    Skips deps because we only need the bundled template files, not a working
    runtime. Returns True on success.
    """
    console.print(
        f"    Falling back to direct extraction from uv-release {from_version}"
    )
    result = subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            "--target",
            str(target),
            f"uv-release=={from_version}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        console.print(
            f"    Fallback install failed: {result.stderr.strip() or result.stdout.strip()}"
        )
        return False
    return True


def _read_workflow_from_install(from_version: str) -> str | None:
    """Install uv-release==version and read the workflow template file.

    Returns None on any failure (install failure or missing file).
    """
    with tempfile.TemporaryDirectory(prefix="uvr-fetch-") as tmp:
        target = Path(tmp)
        if not _install_uv_release(from_version, target):
            return None
        template_path = target / _WORKFLOW_TEMPLATE_REL
        if not template_path.is_file():
            console.print(
                f"    Fallback: {_WORKFLOW_TEMPLATE_REL} not found in"
                f" uv-release {from_version}"
            )
            return None
        return template_path.read_text(encoding="utf-8")


def _read_skills_from_install(
    from_version: str,
) -> dict[str, list[tuple[str, str]]] | None:
    """Install uv-release==version and read every skill template file.

    Walks templates/skills/<skill>/** recursively, returning {skill: [(rel,
    content), ...]}. Returns None on install failure or missing skills dir.
    """
    with tempfile.TemporaryDirectory(prefix="uvr-fetch-") as tmp:
        target = Path(tmp)
        if not _install_uv_release(from_version, target):
            return None
        skills_dir = target / _SKILLS_TEMPLATE_REL
        if not skills_dir.is_dir():
            console.print(
                f"    Fallback: {_SKILLS_TEMPLATE_REL} not found in"
                f" uv-release {from_version}"
            )
            return None
        out: dict[str, list[tuple[str, str]]] = {}
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            entries: list[tuple[str, str]] = []
            for src in sorted(skill_dir.rglob("*")):
                if not src.is_file():
                    continue
                rel = src.relative_to(skill_dir).as_posix()
                entries.append((rel, src.read_text(encoding="utf-8")))
            if entries:
                out[skill_dir.name] = entries
        return out
