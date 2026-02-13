"""Package gamma - depends on beta."""

from pkg_beta import greet as beta_greet

__version__ = "0.1.3"


def greet() -> str:
    """Return a greeting from gamma, including beta's greeting."""
    return f"Hello from gamma! Also, {beta_greet()}"


def gamma_only() -> str:
    """A gamma-specific function."""
    return "This is gamma-only functionality"


def test1_gamma_change() -> str:
    """Test 1: change gamma leaf node."""
    return "gamma changed"
