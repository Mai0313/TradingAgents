"""Textual app shell wiring the Setup and Run screens together.

Exposes :func:`run_tui` as the entrypoint that
:mod:`tradingagents.__main__` dispatches when the user invokes
``tradingagents tui`` (or the ``poe tui`` alias). The app's return
value is the final BUY / SELL / HOLD decision string when a run
completed, or ``None`` when the user cancelled before the pipeline
finished.
"""

from __future__ import annotations

from typing import ClassVar
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from tradingagents.interface.tui.setup_screen import SetupScreen

_STYLES_PATH = Path(__file__).resolve().parent / "styles.tcss"


class TradingAgentsApp(App[str | None]):
    """Top-level Textual application for the TradingAgents TUI.

    The app starts on :class:`SetupScreen` (parameter form). Submitting
    that screen pushes :class:`RunScreen`, which kicks off the live
    pipeline worker. Both screens call :meth:`App.exit` with the final
    decision (or ``None``) when the user is done, so :func:`run_tui`
    can return it to the calling shell command.
    """

    CSS_PATH = _STYLES_PATH

    BINDINGS: ClassVar[list[Binding]] = [Binding("ctrl+q", "quit", "Quit")]

    def on_mount(self) -> None:
        """Push the setup form as soon as the app finishes mounting."""
        self.push_screen(SetupScreen())


def run_tui() -> str | None:
    """Run the interactive TradingAgents TUI.

    A two-screen Textual app:

    1. :class:`SetupScreen` collects every parameter that
       :func:`tradingagents.interface.cli.run_cli` accepts via labelled
       form widgets; defaults match the documented "all defaults" CLI
       invocation.
    2. :class:`RunScreen` mounts a header / phase sidebar / scrollable
       message log / status footer and runs
       :meth:`TradingAgentsGraph.propagate` in a worker thread. Rich
       panels stream back into the log and the sidebar lights up the
       currently-running phase, all reflowing automatically on
       terminal resize (the original motivation for migrating off the
       plain ``rich.console.Console.print`` path).

    Returns:
        str | None: The final BUY / SELL / HOLD decision text returned
        by :meth:`TradingAgentsGraph.process_signal`, or ``None`` when
        the user cancels at the setup screen or quits before the
        pipeline finishes.
    """
    return TradingAgentsApp().run()
