"""The ``uvr workflow publish`` command."""

from __future__ import annotations

import argparse
import sys

from .._args import CommandArgs
from ...intents.configure_publish import ConfigurePublishIntent
from ...planner import compute_plan
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

    try:
        plan = compute_plan(intent)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not plan.jobs:
        workspace = plan.metadata.workspace
        assert workspace is not None
        _print_publish(workspace)
        return

    execute_plan(plan, hooks=None)

    if parsed.clear:
        print("Cleared publish config.")
    else:
        print("Updated publish config.")


def _print_publish(workspace: object) -> None:
    """Print the current publish config."""
    from ...types import Workspace

    assert isinstance(workspace, Workspace)
    pub = workspace.publishing
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
