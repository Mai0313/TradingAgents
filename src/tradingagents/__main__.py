"""Top-level dispatcher for the tradingagents console script.

A thin fire-driven router that exposes run_cli and run_tui as the cli
and tui subcommands respectively. The --help / -h / "help" cases are
intercepted before fire ever sees them so help output is rendered as
Rich panels directly to stdout instead of through fire's default pager
(less-style) UI.

This module doubles as both the "python -m tradingagents" entry point
and the [project.scripts] target in pyproject.toml, so there is
exactly one routing surface.

Examples:
    >>> # tradingagents                     # rich app help (no pager)
    >>> # tradingagents --help              # same as above
    >>> # tradingagents help cli            # rich per-command help
    >>> # tradingagents cli --help          # same as above
    >>> # tradingagents cli --ticker AAPL   # actually run cli
    >>> # tradingagents tui                 # interactive run
    >>> # python -m tradingagents cli ...   # equivalent to the above
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import fire
from rich.console import Console

from tradingagents.interface.cli import run_cli
from tradingagents.interface.tui import run_tui
from tradingagents.interface.help import print_app_help, print_command_help
from tradingagents.interface.reflect import run_reflect
from tradingagents.interface.backtest import run_backtest

if TYPE_CHECKING:
    from collections.abc import Callable

COMMANDS: dict[str, Callable[..., Any]] = {
    "cli": run_cli,
    "tui": run_tui,
    "reflect": run_reflect,
    "backtest": run_backtest,
}
_HELP_FLAGS = frozenset({"--help", "-h"})


def main() -> None:
    """Entry point for the tradingagents console script.

    Routing rules (checked in order before delegating to fire):

    1. No arguments -> top-level Rich help.
    2. First arg is --help, -h, or "help" -> top-level help, or
       per-command help when followed by a known subcommand
       (e.g. tradingagents help cli).
    3. First arg is a known subcommand and any following arg is --help
       or -h -> per-command Rich help.
    4. Otherwise: hand off to :func:`fire.Fire` for actual dispatch.
    """
    args = sys.argv[1:]
    console = Console()

    if not args or args[0] in _HELP_FLAGS or args[0] == "help":
        target = args[1] if len(args) >= 2 else None
        if target and target in COMMANDS:
            print_command_help(console, target, COMMANDS[target])
        else:
            print_app_help(console, COMMANDS)
        return

    cmd_name = args[0]
    if cmd_name in COMMANDS and any(a in _HELP_FLAGS for a in args[1:]):
        print_command_help(console, cmd_name, COMMANDS[cmd_name])
        return

    fire.Fire(COMMANDS, name="tradingagents")


if __name__ == "__main__":
    main()
