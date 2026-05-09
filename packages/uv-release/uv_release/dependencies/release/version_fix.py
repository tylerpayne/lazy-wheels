"""StripDev: remove .devN suffixes from versions before a non-dev release.

When `uvr release` (without --dev) detects dev versions, the ReleaseGuard
raises a UserRecoverableError carrying this fix Job. The CLI executes the
fix locally with user confirmation, then restarts so the DI container
re-resolves from the updated pyproject.toml versions. Nothing here runs
in CI. The release command never modifies versions itself; it only reads
the current git state and plans from it.

The fix is exactly one shell command: `uvr version --bump stable
--packages <names...>`. That's the same `uvr version` the user could type
themselves, so what we display in the Fix block is what literally runs
when they accept.
"""

from __future__ import annotations

from pydantic import Field

from diny import singleton, provider

from ...types.base import Frozen
from ...commands import ShellCommand
from ...types.job import Job
from ..build.build_packages import BuildPackages
from ..params.dev_release import DevRelease
from ..params.release_target import ReleaseTarget
from ...utils.versioning import compute_release_version


@singleton
class StripDev(Frozen):
    """Commands to strip .devN suffixes before release.

    Empty job means versions are already non-dev. Non-empty job is executed
    locally by the CLI (with user confirmation) before the release plan is
    computed.
    """

    job: Job = Field(default_factory=lambda: Job(name="strip-dev"))


@provider(StripDev)
def provide_strip_dev(
    build_packages: BuildPackages,
    dev_release: DevRelease,
    release_target: ReleaseTarget,
) -> StripDev:
    if dev_release.value:
        return StripDev()

    # Find packages whose current version has a .devN suffix.
    needs_strip: list[str] = []
    for name, pkg in build_packages.items.items():
        release_version = compute_release_version(pkg.version)
        if pkg.version.raw != release_version.raw:
            needs_strip.append(name)

    if not needs_strip:
        return StripDev()

    # The strip-dev fix is one literal `uvr version --bump stable` call —
    # which already pins deps, regenerates the lockfile, commits, and (on
    # CI target) pushes. We pass `--no-push` for local target so the user
    # can review before pushing themselves.
    args = ["uvr", "version", "--bump", "stable", "--packages", *needs_strip]
    if release_target.value != "ci":
        args.append("--no-push")

    cmd = ShellCommand(label="Strip dev versions", args=args)
    return StripDev(job=Job(name="strip-dev", commands=[cmd]))
