"""Release intent package: DI-wired provider classes for the release pipeline."""

from .intent import ReleaseIntent as ReleaseIntent

# Import provider modules so @provider decorators register with diny.
from . import build_job as build_job
from . import build_matrix as build_matrix
from . import bump_job as bump_job
from . import download as download
from . import publish_job as publish_job
from . import release_job as release_job
from . import releases as releases
from . import version_fix as version_fix
