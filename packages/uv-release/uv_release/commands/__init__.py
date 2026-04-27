"""All command types. Each command is frozen and knows how to execute itself."""

from __future__ import annotations

from typing import Annotated, Union

from pydantic import Discriminator

from ..types import CommandGroup
from .build import BuildCommand as BuildCommand
from .build import DownloadWheelsCommand as DownloadWheelsCommand
from .file import MakeDirectoryCommand as MakeDirectoryCommand
from .file import WriteFileCommand as WriteFileCommand
from .pyproject import PinDepsCommand as PinDepsCommand
from .pyproject import SetVersionCommand as SetVersionCommand
from .pyproject import UpdateTomlCommand as UpdateTomlCommand
from .pyproject import WriteUvrSectionCommand as WriteUvrSectionCommand
from .release import CreateReleaseCommand as CreateReleaseCommand
from .release import PublishToIndexCommand as PublishToIndexCommand
from .shell import CreateTagCommand as CreateTagCommand
from .shell import ShellCommand as ShellCommand
from .workflow import DispatchWorkflowCommand as DispatchWorkflowCommand
from .workflow import MergeUpgradeCommand as MergeUpgradeCommand

AnyCommand = Annotated[
    Union[
        ShellCommand,
        CreateTagCommand,
        SetVersionCommand,
        PinDepsCommand,
        CreateReleaseCommand,
        PublishToIndexCommand,
        BuildCommand,
        DownloadWheelsCommand,
        MakeDirectoryCommand,
        WriteFileCommand,
        UpdateTomlCommand,
        WriteUvrSectionCommand,
        DispatchWorkflowCommand,
        MergeUpgradeCommand,
        CommandGroup,
    ],
    Discriminator("type"),
]
