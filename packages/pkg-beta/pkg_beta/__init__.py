"""Package beta - depends on alpha."""

from pkg_alpha import greet as alpha_greet

__version__ = "0.1.0"


def greet() -> str:
    """Return a greeting from beta, including alpha's greeting."""
    return f"Hello from beta! Also, {alpha_greet()}"
