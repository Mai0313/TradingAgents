"""Textual-based interactive TUI for TradingAgents.

The TUI is structured as a small Textual app with two screens:

- :class:`SetupScreen` collects every parameter that
  :func:`tradingagents.interface.cli.run_cli` accepts via labelled form
  widgets (``Input`` / ``Select`` / ``SelectionList`` / ``Switch``).
- :class:`RunScreen` shows the live pipeline output: a header with the
  resolved configuration, a sidebar tracking the currently-running
  phase (Market analyst, Bull/Bear debate, Trader, Risk debate, ...),
  a scrollable :class:`textual.widgets.RichLog` carrying the same Rich
  panels the CLI emits, and a footer with the final decision.

The whole stack is built on the existing
:meth:`TradingAgentsGraph.propagate` API: the run worker passes a
:class:`tradingagents.interface.display.MessageRenderer` whose ``emit``
hops back to the Textual main thread via
:meth:`textual.app.App.call_from_thread`, so panel rendering, layout
reflow on resize and graph execution all stay safely decoupled.
"""

from __future__ import annotations

from tradingagents.interface.tui.app import run_tui

__all__ = ["run_tui"]
