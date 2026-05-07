"""ArgumentParser subclass that renders help through the uv_release.ui module.

argparse's default HelpFormatter is plain text. We subclass at the parser
level (not the formatter level) because we want full control over layout —
banner first, then a Commands table, then an Options table — and that's
hard to achieve by overriding individual format_* hooks. The formatter
class is left untouched so usage strings (`uvr release [-h] ...`) still
render via argparse's machinery.
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Any

from .. import ui


class UvrArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that prints --help and errors via the ui design system."""

    def print_help(self, file: Any = None) -> None:
        # argparse calls print_help on stdout for --help. We use the ui
        # console (also stdout) so colors share a single render path.
        if file is not None and file is not sys.stdout:
            super().print_help(file)
            return
        _render_help(self)

    def error(self, message: str) -> Any:
        # Render argparse errors as a single ui.error summary, no detail
        # rows or fix block — the user already knows the command they ran
        # and `--help` is one keystroke away. We rewrite messages that leak
        # internal dest names (e.g. `argument wf_subcommand: ...`).
        summary = _humanize_argparse_error(self, message)
        ui.error(summary)
        # argparse's default error exits 2; preserve that for shell scripts.
        sys.exit(2)


def _render_help(parser: argparse.ArgumentParser) -> None:
    """Render help: banner (top-level only), usage, commands, options."""
    is_root = parser.prog == "uvr"

    if is_root:
        ui.banner(_version())
        ui.console.print()
        if parser.description:
            ui.console.print(parser.description)
            ui.console.print()
    else:
        # Subcommand help: print the canonical argparse usage line so
        # users still see the exact `uvr release [-h] [--where ...]` form.
        ui.console.print(
            f"[uvr.dim]usage:[/] {parser.format_usage().strip().removeprefix('usage: ')}"
        )
        ui.console.print()
        if parser.description:
            ui.console.print(parser.description)
            ui.console.print()

    sub = _find_subparsers(parser)
    if sub is not None:
        ui.section("Commands")
        rows: list[list[str]] = [
            [f"[uvr.cmd]{name}[/]", help_text or ""]
            for name, help_text in _subcommands(sub)
        ]
        ui.print_table(["command", "description"], rows)
        ui.console.print()

    options = _options(parser)
    if options:
        ui.section("Options")
        rows = [[f"[uvr.cmd]{flags}[/]", help_text] for flags, help_text in options]
        ui.print_table(["flag", "description"], rows)
        ui.console.print()


def _find_subparsers(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction[Any] | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _subcommands(
    sub: argparse._SubParsersAction[Any],
) -> list[tuple[str, str]]:
    # `choices` is the dict of name -> sub-parser; `_choices_actions` is the
    # list of help-bearing entries (in registration order). Walk both so we
    # respect order and pick up the help text.
    items: list[tuple[str, str]] = []
    helps = {ca.dest: ca.help or "" for ca in sub._choices_actions}
    for name in sub.choices:
        items.append((name, helps.get(name, "")))
    return items


def _options(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    """All flag-style actions on the parser (skipping subcommands)."""
    out: list[tuple[str, str]] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            continue
        if not action.option_strings:
            continue
        flags = ", ".join(action.option_strings)
        # Append the metavar/choices so the flag column shows e.g.
        # `--where {ci,local}` or `--packages PACKAGES`.
        if action.nargs not in (0, None) or action.choices is not None:
            metavar = _format_metavar(action)
            if metavar:
                flags = f"{flags} {metavar}"
        out.append((flags, action.help or ""))
    return out


_INVALID_CHOICE_RE = re.compile(
    r"^argument (?P<arg>[\w-]+): invalid choice: ['\"](?P<bad>[^'\"]+)['\"]\s*"
    r"\(choose from (?P<choices>.+)\)$"
)


def _humanize_argparse_error(
    parser: argparse.ArgumentParser, message: str
) -> str:
    """Rewrite argparse's raw error string into a one-line user-facing summary.

    Falls back to the raw message when we don't recognize the shape.
    """
    m = _INVALID_CHOICE_RE.match(message)
    if m is not None:
        bad = m.group("bad")
        arg_name = m.group("arg")
        # Distinguish "invalid subcommand" (arg is the subparsers dest, e.g.
        # `wf_subcommand`) from "invalid flag value" (arg is a real flag like
        # `--where`). For subcommands we want a cleaner phrasing without
        # leaking the internal dest name.
        sub = _find_subparsers(parser)
        if sub is not None and sub.dest == arg_name:
            return f"Unknown command {bad!r} for `{parser.prog}`."
        # Flag value: keep the flag name, drop argparse's verbose
        # `(choose from ...)` tail.
        return f"{arg_name}: {bad!r} is not a valid value."

    return message


def _version() -> str:
    """Read uv-release's installed version. Falls back to '?' if not packaged."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("uv-release")
    except PackageNotFoundError:
        return "?"


def _format_metavar(action: argparse.Action) -> str:
    if action.choices is not None:
        return "{" + ",".join(str(c) for c in action.choices) + "}"
    if isinstance(action.metavar, tuple):
        return " ".join(action.metavar)
    if action.metavar is not None:
        return str(action.metavar)
    if action.dest:
        return action.dest.upper()
    return ""
