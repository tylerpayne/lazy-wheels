"""StripDev: remove .devN suffixes from versions before a non-dev release.

When `uvr release` (without --dev) detects dev versions, the ReleaseGuard
raises a UserRecoverableError carrying this fix Job. The CLI executes the
fix locally with user confirmation, then restarts so the DI container
re-resolves from the updated pyproject.toml versions. Nothing here runs
in CI. The release command never modifies versions itself; it only reads
the current git state and plans from it.

The fix is exactly one shell command: `uvr version --bump release
--packages <names...>`. `--bump release` strips only the `.devN` suffix,
so a pre-release dev version like 1.0.0a0.dev0 correctly resolves to
1.0.0a0 (not 1.0.0, which is what `--bump stable` would do). That's the
same `uvr version` the user could type themselves, so what we display in
the Fix block is what literally runs when they accept.
"""

from __future__ import annotations

from pydantic import Field

from diny import singleton, provider

from ...types.base import Frozen
from ...commands import ShellCommand
from ...types.job import Job
from ..build.build_packages import BuildPackages
from ..params.dev_release import DevRelease
from ..params.package_selection import PackageSelection
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
    package_selection: PackageSelection,
) -> StripDev:
    if dev_release.value:
        return StripDev()

    # Trigger only when at least one release target carries a .devN suffix.
    # Once triggered, the fix delegates to `uvr version --bump release`,
    # which selects the same set of packages we'd be releasing (changed
    # since baseline by default) and is a no-op on already-stable versions.
    needs_strip = any(
        compute_release_version(pkg.version).raw != pkg.version.raw
        for pkg in build_packages.items.values()
    )
    if not needs_strip:
        return StripDev()

    # `uvr version --bump release` already pins deps, regenerates the
    # lockfile, commits, and (on CI target) pushes. `--no-push` for local
    # target so the user can review before pushing themselves.
    args = ["uvr", "version", "--bump", "release"]
    if release_target.value != "ci":
        args.append("--no-push")
    # Forward the same package filter the release was invoked with. Without
    # this, `uvr release --packages X` would strip dev on every changed
    # package instead of only X, defeating the user's selection.
    if package_selection.all_packages:
        args.append("--all-packages")
    if package_selection.packages:
        args.extend(["--packages", *sorted(package_selection.packages)])
    if package_selection.exclude_packages:
        args.extend(["--not-packages", *sorted(package_selection.exclude_packages)])

    cmd = ShellCommand(label="Strip dev versions", args=args)
    return StripDev(job=Job(name="strip-dev", commands=[cmd]))
