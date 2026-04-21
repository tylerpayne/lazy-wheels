"""InstallIntent: install packages from GitHub releases or local wheels."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..commands import ShellCommand
from ..states.github import LatestReleaseTags
from ..states.worktree import Worktree
from ..types import Command, Job, Package, Plan, Tag


def _parse_spec(spec: str) -> tuple[str, str]:
    """Parse a package spec like 'pkg' or 'pkg==1.0.0' into (name, version)."""
    from packaging.requirements import Requirement

    req = Requirement(spec)
    version = ""
    for specifier in req.specifier:
        if specifier.operator == "==":
            version = specifier.version
            break
    return str(req.name), version


class InstallIntent(BaseModel):
    """Intent to install packages from GitHub releases or local wheels."""

    model_config = ConfigDict(frozen=True)

    type: Literal["install"] = "install"
    packages: list[str] = Field(default_factory=list)
    dist: str = ""
    repo: str = ""

    def guard(self) -> None:
        """Check that we have something to install."""
        if not self.packages and not self.dist:
            msg = "Specify at least one package or --dist directory."
            raise ValueError(msg)

        if self.dist and not Path(self.dist).is_dir():
            msg = f"Directory not found: {self.dist}"
            raise ValueError(msg)

    def plan(
        self, *, worktree: Worktree, latest_release_tags: LatestReleaseTags
    ) -> Plan:
        """(state, intent) -> plan."""
        commands: list[Command] = []

        if self.dist:
            dist_dir = Path(self.dist)
            if self.packages:
                wheel_paths: list[str] = []
                for spec in self.packages:
                    name = spec.split("@")[0]
                    dist_name = Package.format_dist_name(name)
                    found = sorted(dist_dir.glob(f"{dist_name}-*.whl"))
                    if not found:
                        msg = f"No wheel found for '{name}' in {dist_dir}"
                        raise ValueError(msg)
                    wheel_paths.append(str(found[-1]))
            else:
                wheel_paths = [str(w) for w in sorted(dist_dir.glob("*.whl"))]
                if not wheel_paths:
                    msg = f"No wheels found in {dist_dir}"
                    raise ValueError(msg)

            commands.append(
                ShellCommand(
                    label=f"Install {len(wheel_paths)} wheel(s) from {self.dist}",
                    args=[
                        "uv",
                        "pip",
                        "install",
                        "--find-links",
                        str(dist_dir),
                        *wheel_paths,
                    ],
                )
            )
        else:
            repo_name = self.repo or worktree.repo
            cache_dir = Path.home() / ".uvr" / "cache"

            for spec in self.packages:
                name, version = _parse_spec(spec)
                dist_name = Package.format_dist_name(name)

                if version:
                    tag = f"{Tag.tag_prefix(name)}{version}"
                else:
                    tag = latest_release_tags.tags.get(name, "")

                if not tag:
                    continue

                commands.append(
                    ShellCommand(
                        label=f"Download {name} {tag}",
                        args=[
                            "gh",
                            "release",
                            "download",
                            tag,
                            "--repo",
                            repo_name,
                            "--dir",
                            str(cache_dir),
                            "--pattern",
                            f"{dist_name}-*.whl",
                            "--clobber",
                        ],
                    )
                )

            if commands:
                # Install all downloaded wheels
                commands.append(
                    ShellCommand(
                        label="Install downloaded wheels",
                        args=[
                            "uv",
                            "pip",
                            "install",
                            "--find-links",
                            str(cache_dir),
                            ".",
                        ],
                        check=False,
                    )
                )

        return Plan(jobs=[Job(name="install", commands=commands)])
