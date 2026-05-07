"""uv_release.ui — the design system.

Every uvr command imports from here and never from `rich` directly. This
keeps the visual grammar (bold-magenta titles, hyphen rules, ASCII bars,
magenta arrows) consistent across the whole CLI.
"""

from .badge import badge, badge_markup
from .banner import banner
from .confirm import confirm
from .console import THEME, console
from .error import error
from .hint import hint
from .kv import kv
from .pipeline import Route, Step, pipeline
from .progress import progress_line, progress_lines
from .section import section
from .spinner import spinner, spinner_done
from .table import make_table, print_table


__all__ = [
    "THEME",
    "Route",
    "Step",
    "badge",
    "badge_markup",
    "banner",
    "confirm",
    "console",
    "error",
    "hint",
    "kv",
    "make_table",
    "pipeline",
    "print_table",
    "progress_line",
    "progress_lines",
    "section",
    "spinner",
    "spinner_done",
]
