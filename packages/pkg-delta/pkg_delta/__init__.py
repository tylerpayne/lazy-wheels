"""Package delta - depends on alpha (sibling of beta)."""

from pkg_alpha import greet as alpha_greet

__version__ = "0.1.0"


def greet() -> str:
    """Return a greeting from delta, including alpha's greeting."""
    return f"Hello from delta! Also, {alpha_greet()}"
