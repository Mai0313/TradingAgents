"""Live pipeline screen for the TradingAgents TUI.

Shows the running graph in three regions:

- A docked header rendering the resolved run configuration via the
  same Rich panel the CLI prints (so reflow on resize works the way
  ``rich.console.Console.print`` could not).
- A horizontal body split into a phase sidebar (Market analyst,
  Bull/Bear debate, Trader, Risk debate, Final) and a scrollable
  :class:`textual.widgets.RichLog` carrying every message Rich panel
  emitted by :class:`MessageRenderer`.
- A docked footer with run status (initialising, running, done, error).

The blocking :meth:`TradingAgentsGraph.propagate` call is dispatched to
a worker thread; both panel writes and sidebar updates are funnelled
back to the Textual event loop via :meth:`App.call_from_thread`, the
only thread-safe path into Textual widgets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar
import logging

from textual import work
from rich.text import Text
from rich.panel import Panel
from textual.screen import Screen
from textual.binding import Binding
from textual.widgets import Static, RichLog
from textual.containers import Vertical, Horizontal

from tradingagents.config import TradingAgentsConfig
from tradingagents.interface.display import (
    MessageRenderer,
    make_run_header_panel,
    make_final_decision_panel,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.interface.tui.phase_tracker import Phase, derive_phases

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from tradingagents.interface.tui.params import SetupParams
    from tradingagents.agents.utils.agent_states import AgentState

logger = logging.getLogger(__name__)

_PHASE_ICONS: dict[str, str] = {"pending": "o", "running": ">", "done": "v"}


class PhaseRow(Static):
    """One row in the phase sidebar.

    Rendered as a compact ``icon | label | progress`` line whose CSS
    class encodes the current status (``-pending`` / ``-running`` /
    ``-done``) so :file:`styles.tcss` can colour them appropriately.
    """

    def __init__(self, phase: Phase) -> None:
        """Create a row matching ``phase``.

        Args:
            phase (Phase): Initial phase data; the widget id is taken
                from ``phase.id`` so later updates can target it via
                ``query_one``.
        """
        super().__init__(id=phase.id, classes=f"phase-row -{phase.status}")
        self._phase = phase

    def render(self) -> Text:
        """Compose the row content as a Rich Text line.

        Returns:
            Text: An icon, the phase label, and an optional progress
            counter, separated by a space.
        """
        icon = _PHASE_ICONS.get(self._phase.status, "?")
        suffix = f"  {self._phase.progress}" if self._phase.progress else ""
        return Text.from_markup(f"{icon}  {self._phase.label}{suffix}")

    def update_phase(self, phase: Phase) -> None:
        """Replace the row's contents and CSS class with ``phase``.

        Args:
            phase (Phase): The new phase data; only fields whose values
                differ from the previous render trigger a refresh.
        """
        if phase == self._phase:
            return
        self._phase = phase
        self.remove_class("-pending", "-running", "-done")
        self.add_class(f"-{phase.status}")
        self.refresh()


class RunScreen(Screen[None]):
    """Drive a single :meth:`TradingAgentsGraph.propagate` run.

    The screen composes the static layout up-front, then kicks off a
    worker thread on mount. The worker streams panel renderables back
    via :meth:`App.call_from_thread`, which is the only thread-safe way
    to mutate Textual widgets from outside the event loop.
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit_screen", "Quit"),
        Binding("ctrl+c", "quit_screen", "Quit"),
    ]

    def __init__(self, params: SetupParams) -> None:
        """Store the run parameters; widgets are built in :meth:`compose`.

        Args:
            params (SetupParams): The validated parameter bundle from
                :class:`SetupScreen`.
        """
        super().__init__()
        self.params = params
        self._log: RichLog | None = None
        self._status: Static | None = None
        self._final_decision: str | None = None
        self._config = TradingAgentsConfig(
            llm_provider=params.llm_provider,
            deep_think_llm=params.deep_think_llm,
            quick_think_llm=params.quick_think_llm,
            max_debate_rounds=params.max_debate_rounds,
            max_risk_discuss_rounds=params.max_risk_discuss_rounds,
            max_recur_limit=params.max_recur_limit,
            reasoning_effort=params.reasoning_effort,
            response_language=params.response_language,
        )

    def compose(self) -> ComposeResult:
        """Build the screen layout.

        Yields:
            ComposeResult: Header panel, sidebar with one
            :class:`PhaseRow` per pipeline phase, the messages
            :class:`RichLog`, and a status footer.
        """
        yield Static(
            make_run_header_panel(
                ticker=self.params.ticker, trade_date=self.params.date, config=self._config
            ),
            id="run-header",
        )
        with Horizontal(id="run-body"):
            with Vertical(id="phase-sidebar"):
                yield Static("Phases", id="phase-sidebar-title")
                for phase in self._initial_phases():
                    yield PhaseRow(phase)
            yield RichLog(
                id="messages", wrap=True, markup=False, highlight=False, auto_scroll=True
            )
        yield Static("Initialising...", id="run-status")

    def on_mount(self) -> None:
        """Cache widget references and kick off the pipeline worker."""
        self._log = self.query_one("#messages", RichLog)
        self._status = self.query_one("#run-status", Static)
        self.run_pipeline()

    def action_quit_screen(self) -> None:
        """Exit the app, returning the final decision (or None) to ``run_tui``."""
        self.app.exit(self._final_decision)

    @work(thread=True, exclusive=True)
    def run_pipeline(self) -> None:
        """Run :meth:`TradingAgentsGraph.propagate` on a worker thread.

        Constructs a :class:`MessageRenderer` whose ``emit`` defers each
        Rich renderable to the Textual event loop, and an ``on_state``
        hook that recomputes the sidebar phase list from the latest
        :class:`AgentState` snapshot. All UI mutations are routed
        through :meth:`App.call_from_thread` via :meth:`_safe_call` so
        the worker unwinds quietly when the user quits mid-run; a
        broken hook can never abort a paid LLM call once it has
        started.
        """
        log = self._log
        if log is None:
            raise RuntimeError("run_pipeline invoked before on_mount cached the RichLog")

        def emit(renderable: object) -> None:
            self._safe_call(log.write, renderable)

        renderer = MessageRenderer(emit=emit)

        def on_state(state: AgentState) -> None:
            self._safe_call(self._update_phases_from_state, state)

        self._safe_call(self._set_status, "Running pipeline...")

        try:
            ta = TradingAgentsGraph(
                debug=self.params.debug,
                config=self._config,
                selected_analysts=self.params.selected_analysts,
            )
            _, decision = ta.propagate(
                self.params.ticker, self.params.date, on_message=renderer, on_state=on_state
            )
        except Exception as exc:
            logger.exception("TUI pipeline run failed")
            self._safe_call(self._on_error, exc)
            return

        self._safe_call(self._on_done, decision)

    def _safe_call(self, func: object, *args: object) -> bool:
        """Schedule ``func(*args)`` on the Textual event loop, no-op if shut down.

        Resolving ``self.app`` from a worker thread relies on
        Textual's ``active_app`` ContextVar, which is unset once the
        app starts tearing down (e.g. user pressed q while the
        pipeline was mid-stream). A bare ``self.app.call_from_thread``
        in that window raises ``NoActiveAppError`` and dumps a
        traceback for every subsequent ``on_message`` callback. This
        wrapper catches that case so the worker can finish unwinding
        silently.

        Args:
            func (object): A callable to invoke on the main thread.
            *args (object): Positional arguments forwarded to ``func``.

        Returns:
            bool: True when the call was scheduled, False when the app
            had already torn down.
        """
        try:
            app = self.app
        except Exception:
            return False
        try:
            app.call_from_thread(func, *args)
        except Exception:
            logger.debug("call_from_thread failed; app likely shutting down", exc_info=True)
            return False
        return True

    def _initial_phases(self) -> list[Phase]:
        """Phases derived from a None state -> all pending except the first.

        Returns:
            list[Phase]: The initial phase list rendered before the
            first stream chunk arrives.
        """
        return derive_phases(
            None,
            selected_analysts=self.params.selected_analysts,
            max_debate_rounds=self.params.max_debate_rounds,
            max_risk_discuss_rounds=self.params.max_risk_discuss_rounds,
        )

    def _update_phases_from_state(self, state: AgentState) -> None:
        """Refresh every :class:`PhaseRow` from the latest ``AgentState``.

        Args:
            state (AgentState): The most recent streamed snapshot.
        """
        phases = derive_phases(
            state,
            selected_analysts=self.params.selected_analysts,
            max_debate_rounds=self.params.max_debate_rounds,
            max_risk_discuss_rounds=self.params.max_risk_discuss_rounds,
        )
        for phase in phases:
            try:
                row = self.query_one(f"#{phase.id}", PhaseRow)
            except Exception:
                logger.debug("Phase row %s not found", phase.id, exc_info=True)
                continue
            row.update_phase(phase)

    def _set_status(self, text: str) -> None:
        """Update the docked footer status line.

        Args:
            text (str): Plain text to display.
        """
        if self._status is not None:
            self._status.update(text)

    def _on_done(self, decision: str) -> None:
        """Append the final-decision panel and switch the footer to Done.

        Args:
            decision (str): The BUY / SELL / HOLD text returned by
                :meth:`TradingAgentsGraph.process_signal`.
        """
        self._final_decision = decision
        if self._log is not None:
            self._log.write(make_final_decision_panel(decision))
        self._set_status(
            f"Done. Final decision: {decision.strip() or '(empty)'}  -  press q to quit"
        )

    def _on_error(self, exc: BaseException) -> None:
        """Append an error panel and surface the exception in the footer.

        Args:
            exc (BaseException): The exception raised by the worker.
        """
        if self._log is not None:
            self._log.write(
                Panel(
                    Text(f"{type(exc).__name__}: {exc}", style="bold red"),
                    title="[bold red]Pipeline Error[/]",
                    title_align="left",
                    border_style="red",
                )
            )
        self._set_status(f"Failed: {type(exc).__name__}: {exc}  -  press q to quit")
