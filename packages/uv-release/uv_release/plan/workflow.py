"""Assemble a Workflow from jobs with pre-computed execution order."""

from __future__ import annotations

from ..graph import topo_sort
from ..types import Job, Workflow


def create_workflow(
    validate_job: Job,
    build_job: Job,
    release_job: Job,
    publish_job: Job,
    bump_job: Job,
) -> Workflow:
    """Assemble a Workflow with the 5 required jobs, DAG edges, and execution order."""
    jobs = {
        "uvr-validate": Job(
            name="uvr-validate",
            commands=validate_job.commands,
        ),
        "uvr-build": Job(
            name="uvr-build",
            needs=["uvr-validate"],
            commands=build_job.commands,
            pre_hook="pre_build",
            post_hook="post_build",
        ),
        "uvr-release": Job(
            name="uvr-release",
            needs=["uvr-build"],
            commands=release_job.commands,
            pre_hook="pre_release",
            post_hook="post_release",
        ),
        "uvr-publish": Job(
            name="uvr-publish",
            needs=["uvr-release"],
            commands=publish_job.commands,
            pre_hook="pre_publish",
            post_hook="post_publish",
        ),
        "uvr-bump": Job(
            name="uvr-bump",
            needs=["uvr-publish"],
            commands=bump_job.commands,
            pre_hook="pre_bump",
            post_hook="post_bump",
        ),
    }
    job_order = topo_sort({name: job.needs for name, job in jobs.items()})
    return Workflow(jobs=jobs, job_order=job_order)
