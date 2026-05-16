"""PackageSelection: which packages the user requested."""

from diny import singleton

from ...types.base import Frozen


@singleton
class PackageSelection(Frozen):
    """Seeded by CLI. Controls which packages are targeted."""

    all_packages: bool = False
    packages: frozenset[str] = frozenset()
    exclude_packages: frozenset[str] = frozenset()
    # When set, workspace packages reachable via [build-system].requires of the
    # selected packages are also treated as targets (built from source into
    # dist/ rather than downloaded as released wheels into deps/).
    and_build_system_requirements: bool = False
    # Same as above but for runtime [project.dependencies] entries.
    and_dependencies: bool = False
