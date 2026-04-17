"""DownloadIntent: download wheels from GitHub releases."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..commands import MakeDirectoryCommand, ShellCommand
from ..types import Command, Job, Package, Plan, Workspace
from ..states.github import find_latest_release_tag, infer_gh_repo


class DownloadIntent(BaseModel):
    """Intent to download wheels from a GitHub release or CI run."""

    model_config = ConfigDict(frozen=True)

    type: Literal["download"] = "download"
    package: str = ""
    release_tag: str = ""
    run_id: str = ""
    repo: str = ""
    output: str = "dist"

    def guard(self, workspace: Workspace) -> None:
        """Check that we have enough info to download."""
        if not self.package and not self.run_id:
            msg = "Specify a package name or --run-id."
            raise ValueError(msg)

    def plan(self, workspace: Workspace) -> Plan:
        """(state, intent) -> plan."""
        gh_repo = self.repo or infer_gh_repo() or ""
        output_dir = self.output

        commands: list[Command] = [
            MakeDirectoryCommand(
                label=f"Create output directory {output_dir}",
                path=output_dir,
            ),
        ]

        if self.run_id:
            dist_name = ""
            if self.package:
                dist_name = Package.format_dist_name(self.package)
            cmd_args = [
                "gh",
                "run",
                "download",
                self.run_id,
                "--repo",
                gh_repo,
                "--dir",
                output_dir,
            ]
            if dist_name:
                cmd_args.extend(["--pattern", f"*{dist_name}*"])
            commands.append(
                ShellCommand(
                    label=f"Download artifacts from run {self.run_id}", args=cmd_args
                )
            )
        else:
            dist_name = Package.format_dist_name(self.package)
            tag = self.release_tag or find_latest_release_tag(self.package, gh_repo)
            if not tag:
                msg = f"No release found for '{self.package}'."
                raise ValueError(msg)

            commands.append(
                ShellCommand(
                    label=f"Download {self.package} from {tag}",
                    args=[
                        "gh",
                        "release",
                        "download",
                        tag,
                        "--repo",
                        gh_repo,
                        "--dir",
                        output_dir,
                        "--pattern",
                        f"{dist_name}-*.whl",
                        "--clobber",
                    ],
                )
            )

        return Plan(jobs=[Job(name="download", commands=commands)])
