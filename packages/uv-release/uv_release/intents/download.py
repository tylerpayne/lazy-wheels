"""DownloadIntent: download wheels from GitHub releases."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..commands import MakeDirectoryCommand, ShellCommand
from ..states.github import LatestReleaseTags
from ..states.worktree import Worktree
from ..types import Command, Job, Package, Plan


class DownloadIntent(BaseModel):
    """Intent to download wheels from a GitHub release or CI run."""

    model_config = ConfigDict(frozen=True)

    type: Literal["download"] = "download"
    package: str = ""
    release_tag: str = ""
    run_id: str = ""
    repo: str = ""
    output: str = "dist"

    def guard(self) -> None:
        """Check that we have enough info to download."""
        if not self.package and not self.run_id:
            msg = "Specify a package name or --run-id."
            raise ValueError(msg)

    def plan(
        self, *, worktree: Worktree, latest_release_tags: LatestReleaseTags
    ) -> Plan:
        """(state, intent) -> plan."""
        repo_name = self.repo or worktree.repo
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
                repo_name,
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
            tag = self.release_tag or latest_release_tags.tags.get(self.package, "")
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
                        repo_name,
                        "--dir",
                        output_dir,
                        "--pattern",
                        f"{dist_name}-*.whl",
                        "--clobber",
                    ],
                )
            )

        return Plan(jobs=[Job(name="download", commands=commands)])
