"""ConfigureRunnersJob: mutate [tool.uvr.runners] in pyproject.toml."""

from __future__ import annotations

from diny import singleton, provider

from ...commands import WriteUvrSectionCommand
from ...types.job import Job
from ..config.uvr_runners import UvrRunners
from ..params.configure_params import ConfigureRunnersParams


@singleton
class ConfigureRunnersJob(Job):
    """Write updated runners section. Empty = show mode."""


@provider(ConfigureRunnersJob)
def provide_configure_runners_job(
    runners: UvrRunners,
    params: ConfigureRunnersParams,
) -> ConfigureRunnersJob:
    has_mutations = params.add or params.remove or params.clear

    if not has_mutations:
        return ConfigureRunnersJob(name="configure-runners")

    matrix = {k: list(v) for k, v in runners.items.items()}

    if params.clear:
        if params.package:
            matrix.pop(params.package, None)
        else:
            matrix.clear()
    else:
        if not params.package:
            raise ValueError("Specify --package when adding or removing runners.")

        pkg_runners = list(matrix.get(params.package, []))

        for spec in params.add:
            labels = _parse_runner_spec(spec)
            if labels not in pkg_runners:
                pkg_runners.append(labels)

        for spec in params.remove:
            labels = _parse_runner_spec(spec)
            if labels in pkg_runners:
                pkg_runners.remove(labels)

        if pkg_runners:
            matrix[params.package] = pkg_runners
        else:
            matrix.pop(params.package, None)

    return ConfigureRunnersJob(
        name="configure-runners",
        commands=[
            WriteUvrSectionCommand(
                label="Update [tool.uvr.runners]", section="runners", data=matrix
            )
        ],
    )


def _parse_runner_spec(spec: str) -> list[str]:
    """Parse a runner spec like 'self-hosted, linux, x64'.

    Rejects JSON-style input with quotes to avoid double-escaping in TOML.
    """
    stripped = spec.strip()
    if '"' in stripped or "'" in stripped:
        raise ValueError(
            f"Runner spec must not contain quotes: {spec}. "
            "Use comma-separated labels like: self-hosted, linux, x64"
        )
    stripped = stripped.strip("[]")
    return [label.strip() for label in stripped.split(",")]
