"""ConfigurePublishJob: mutate [tool.uvr.publish] in pyproject.toml."""

from __future__ import annotations

from typing import Any

from diny import singleton, provider

from ...commands import WriteUvrSectionCommand
from ...types.job import Job
from ..config.uvr_publishing import UvrPublishing
from ..params.configure_params import ConfigurePublishParams


@singleton
class ConfigurePublishJob(Job):
    """Write updated publish section. Empty = show mode."""


@provider(ConfigurePublishJob)
def provide_configure_publish_job(
    publishing: UvrPublishing,
    params: ConfigurePublishParams,
) -> ConfigurePublishJob:
    has_mutations = (
        params.index is not None
        or params.environment is not None
        or params.trusted_publishing is not None
        or params.include_packages
        or params.exclude_packages
        or params.remove_packages
        or params.clear
    )
    if not has_mutations:
        return ConfigurePublishJob(name="configure-publish")

    if params.clear:
        data: dict[str, Any] = {}
    else:
        data = {}
        index = params.index if params.index is not None else publishing.index
        environment = (
            params.environment
            if params.environment is not None
            else publishing.environment
        )
        trusted = (
            params.trusted_publishing
            if params.trusted_publishing is not None
            else publishing.trusted_publishing
        )

        if index:
            data["index"] = index
        if environment:
            data["environment"] = environment
        data["trusted-publishing"] = trusted

        include = set(publishing.include)
        exclude = set(publishing.exclude)
        include |= set(params.include_packages)
        exclude |= set(params.exclude_packages)
        include -= set(params.remove_packages)
        exclude -= set(params.remove_packages)

        if include:
            data["include"] = sorted(include)
        if exclude:
            data["exclude"] = sorted(exclude)

    return ConfigurePublishJob(
        name="configure-publish",
        commands=[
            WriteUvrSectionCommand(
                label="Update [tool.uvr.publish]", section="publish", data=data
            )
        ],
    )
