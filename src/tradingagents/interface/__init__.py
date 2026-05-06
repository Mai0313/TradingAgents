"""Interactive interfaces for TradingAgents.

The user-facing entry point lives in :mod:`tradingagents.__main__` (so
"python -m tradingagents" and the tradingagents console script share
exactly one routing surface). This subpackage holds the implementation
modules that __main__ dispatches to:

- cli: A flag-driven runner suitable for non-interactive invocation
  (pipe / redirect / CI friendly; Rich panels printed to stdout).
- tui: A Textual app with a setup form and a live run screen whose
  layout reflows on terminal resize -- the upgrade from the legacy
  ``questionary`` + ``rich.print`` flow.
- display: Rich panel builders shared by both modes; CLI emits via
  ``Console.print``, the TUI emits via a thread-safe ``RichLog.write``.
- help: Rich-based help renderer (replaces fire's pager-based help).
"""

from tradingagents.interface.cli import run_cli
from tradingagents.interface.tui import run_tui

__all__ = ["run_cli", "run_tui"]
