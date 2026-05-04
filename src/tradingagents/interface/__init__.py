"""Interactive interfaces for TradingAgents.

The user-facing entry point lives in :mod:`tradingagents.__main__` (so
"python -m tradingagents" and the tradingagents console script share
exactly one routing surface). This subpackage holds the implementation
modules that __main__ dispatches to:

- cli: A flag-driven runner suitable for non-interactive invocation.
- tui: A questionary-driven interactive runner.
- display: Rich-based renderers for LangChain messages and run summaries.
- help: Rich-based help renderer (replaces fire's pager-based help).
"""

from tradingagents.interface.cli import run_cli
from tradingagents.interface.tui import run_tui

__all__ = ["run_cli", "run_tui"]
