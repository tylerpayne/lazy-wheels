"""The ``uvr workflow publish`` command."""

from __future__ import annotations

import argparse

from .._args import CommandArgs, compute_plan_or_exit
from ...intents.configure_publish import ConfigurePublishIntent
from ...execute import execute_plan


class PublishConfigArgs(CommandArgs):
    """Typed arguments for ``uvr workflow publish``."""

    index: str | None = None
    environment: str | None = None
    trusted_publishing: str | None = None
    include_packages: list[str] | None = None
    exclude_packages: list[str] | None = None
    remove_packages: list[str] | None = None
    clear: bool = False


def cmd_publish_config(args: argparse.Namespace) -> None:
    """Manage index publishing config in [tool.uvr.publish]."""
    parsed = PublishConfigArgs.from_namespace(args)

    intent = ConfigurePublishIntent(
        index=parsed.index,
        environment=parsed.environment,
        trusted_publishing=parsed.trusted_publishing,
        add_include=parsed.include_packages or [],
        add_exclude=parsed.exclude_packages or [],
        remove_packages=parsed.remove_packages or [],
        clear=parsed.clear,
    )

    plan = compute_plan_or_exit(intent)

    if not plan.jobs:
        uvr_state = plan.metadata.uvr_state
        assert uvr_state is not None
        _print_publish(uvr_state)
        return

    execute_plan(plan, hooks=None)

    if parsed.clear:
        print("Cleared publish config.")
    else:
        print("Updated publish config.")


def _print_publish(uvr_state: object) -> None:
    """Print the current publish config."""
    from ...states.uvr_state import UvrState

    assert isinstance(uvr_state, UvrState)
    pub = uvr_state.publishing
    if not any([pub.index, pub.environment, pub.include, pub.exclude]):
        print("No publish config set. All packages publish to the default index.")
        return

    if pub.index:
        print(f"  index:              {pub.index}")
    if pub.environment:
        print(f"  environment:        {pub.environment}")
    print(f"  trusted-publishing: {pub.trusted_publishing}")
    if pub.include:
        print(f"  include:            {', '.join(sorted(pub.include))}")
    if pub.exclude:
        print(f"  exclude:            {', '.join(sorted(pub.exclude))}")
