"""uv-release: footgun-free release management for uv workspaces."""

from importlib.metadata import version as _pkg_version

from .shared.hooks import ReleaseHook
from .shared.models import ReleasePlan

__version__ = _pkg_version("uv-release")
__all__ = ["ReleaseHook", "ReleasePlan", "__version__"]
