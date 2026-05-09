"""ConfigureJob: mutate [tool.uvr.config] in pyproject.toml."""

from __future__ import annotations

from typing import Any

from diny import singleton, provider

from ...commands import WriteUvrSectionCommand
from ...types.job import Job
from ..config.uvr_config import UvrConfig
from ..params.configure_params import ConfigureParams


@singleton
class ConfigureJob(Job):
    """Write updated config section. Empty = show mode (no mutations)."""


@provider(ConfigureJob)
def provide_configure_job(
    config: UvrConfig,
    params: ConfigureParams,
) -> ConfigureJob:
    has_mutations = (
        params.latest is not None
        or params.include_packages
        or params.exclude_packages
        or params.remove_packages
        or params.clear
    )
    if not has_mutations:
        return ConfigureJob(name="configure")

    data: dict[str, Any] = {"python_version": config.python_version}

    # Preserve version tracking fields that other commands manage.
    if config.workflow_version:
        data["workflow-version"] = config.workflow_version
    if config.skill_version:
        data["skill-version"] = config.skill_version

    if params.clear:
        # Keep python_version and version fields, drop everything else.
        pass
    else:
        latest = params.latest if params.latest is not None else config.latest_package
        if latest:
            data["latest"] = latest

        include = set(config.include)
        exclude = set(config.exclude)
        include |= set(params.include_packages)
        exclude |= set(params.exclude_packages)
        include -= set(params.remove_packages)
        exclude -= set(params.remove_packages)

        if include:
            data["include"] = sorted(include)
        if exclude:
            data["exclude"] = sorted(exclude)

    return ConfigureJob(
        name="configure",
        commands=[
            WriteUvrSectionCommand(
                label="Update [tool.uvr.config]", section="config", data=data
            )
        ],
    )
