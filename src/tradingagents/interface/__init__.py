"""User-facing interfaces for TradingAgents.

This package collects every entry point a user (or downstream service) might
talk to:

* :mod:`tradingagents.interface.cli` — `fire`-based command-line interface.
* :mod:`tradingagents.interface.tui` — interactive `questionary` runner.
* :mod:`tradingagents.interface.display` — Rich console + LangChain message
  pretty-printer shared by every front end.

Future front ends (REST API, WebUI, gRPC, ...) belong here too so they can
share the display utilities and a single mental model of "interfaces".
"""

from .cli import main
from .tui import run_tui
from .display import console, print_header, print_summary, print_decision, pretty_print_message

__all__ = [
    "console",
    "main",
    "pretty_print_message",
    "print_decision",
    "print_header",
    "print_summary",
    "run_tui",
]
