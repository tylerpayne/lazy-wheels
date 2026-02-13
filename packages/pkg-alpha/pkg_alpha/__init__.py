"""Package alpha - a dummy package with no dependencies."""

__version__ = "0.1.1"


def greet() -> str:
    """Return a greeting from alpha."""
    return "Hello from alpha!"


def alpha_feature() -> str:
    """A new feature in alpha."""
    return "New alpha feature!"


def test2_alpha_change() -> str:
    """Test 2: change alpha root node."""
    return "alpha changed - should cascade to all"
