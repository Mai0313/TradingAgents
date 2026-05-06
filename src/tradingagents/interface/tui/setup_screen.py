"""Form-style setup screen for the TradingAgents TUI.

Replaces the legacy questionary prompt sequence with a single Textual
screen whose widgets cover every parameter that
:func:`tradingagents.interface.cli.run_cli` accepts. Defaults match the
documented "all defaults" CLI invocation, so a user can press Start
without editing anything to reproduce
``tradingagents cli`` with no flags.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, get_args
import datetime

from pydantic import ValidationError
from textual.screen import Screen
from textual.binding import Binding
from textual.widgets import Input, Label, Button, Select, Static, Switch, Checkbox
from textual.containers import Horizontal, VerticalScroll

from tradingagents.llm import LLMProvider, ReasoningEffort
from tradingagents.config import ResponseLanguage
from tradingagents.graph.setup import SUPPORTED_ANALYSTS
from tradingagents.interface.tui.params import SetupParams
from tradingagents.interface.tui.run_screen import RunScreen

if TYPE_CHECKING:
    from textual.app import ComposeResult


class SetupScreen(Screen[None]):
    """Collect run parameters via a Textual form, then push :class:`RunScreen`.

    The screen owns every form widget; values are read directly from
    those widgets at submit time and fed into :class:`SetupParams` so
    Pydantic does the per-field and cross-field validation.
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "start", "Start"),
    ]

    def __init__(self) -> None:
        """Initialise the screen with default values matching :func:`run_cli`."""
        super().__init__()
        self._defaults = SetupParams()

    def compose(self) -> ComposeResult:
        """Build the setup form layout.

        Yields:
            ComposeResult: The widgets that make up the form, including
            text inputs, selects, the analyst checkboxes row, and the
            Start / Cancel buttons.
        """
        today = datetime.date.today().strftime("%Y-%m-%d")
        with VerticalScroll(id="setup-scroll"):
            yield Static("TradingAgents - TUI", id="setup-title")
            yield Static(
                "Tab/Shift+Tab to navigate fields. Defaults match the "
                "tradingagents cli with no flags. Esc cancels, Ctrl+S starts.",
                id="setup-hint",
            )

            yield from self._text_row("ticker", "Ticker", self._defaults.ticker)
            yield from self._text_row("date", "Trade Date (YYYY-MM-DD)", today)
            yield from self._select_row(
                "llm_provider",
                "LLM Provider",
                list(get_args(LLMProvider)),
                self._defaults.llm_provider,
            )
            yield from self._text_row(
                "deep_think_llm", "Deep-Thinking LLM", self._defaults.deep_think_llm
            )
            yield from self._text_row(
                "quick_think_llm", "Quick-Thinking LLM", self._defaults.quick_think_llm
            )
            yield from self._select_row(
                "reasoning_effort",
                "Reasoning Effort",
                list(get_args(ReasoningEffort)),
                self._defaults.reasoning_effort,
            )
            yield from self._select_row(
                "response_language",
                "Response Language",
                list(get_args(ResponseLanguage)),
                self._defaults.response_language,
            )

            with Horizontal(classes="form-row"):
                yield Label("Analysts", classes="form-label")
                with Horizontal(classes="form-checkboxes", id="analyst-checkboxes"):
                    for analyst in SUPPORTED_ANALYSTS:
                        yield Checkbox(analyst, value=True, id=f"analyst-{analyst}")

            yield from self._int_row(
                "max_debate_rounds",
                "Max Bull/Bear Debate Rounds",
                self._defaults.max_debate_rounds,
            )
            yield from self._int_row(
                "max_risk_discuss_rounds",
                "Max Risk-Management Debate Rounds",
                self._defaults.max_risk_discuss_rounds,
            )
            yield from self._int_row(
                "max_recur_limit", "Max Recursion Limit (>= 25)", self._defaults.max_recur_limit
            )

            with Horizontal(classes="form-row"):
                yield Label("Debug Streaming", classes="form-label")
                yield Switch(value=self._defaults.debug, id="debug")

            yield Static("", id="setup-error")

            with Horizontal(id="actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Start", id="start", variant="primary")

    def _text_row(self, field_id: str, label: str, default: str) -> list[Any]:
        """Build a labelled text input row.

        Args:
            field_id (str): DOM id (also serves as the SetupParams field name).
            label (str): The label rendered to the left of the input.
            default (str): Pre-filled input value.

        Returns:
            list[Any]: A single-element list containing the composed
            Horizontal row, returned as a list so callers can ``yield from``.
        """
        return [
            Horizontal(
                Label(label, classes="form-label"),
                Input(value=default, id=field_id, classes="form-input"),
                classes="form-row",
            )
        ]

    def _int_row(self, field_id: str, label: str, default: int) -> list[Any]:
        """Build a labelled integer input row.

        Args:
            field_id (str): DOM id matching the SetupParams field name.
            label (str): Display label.
            default (int): Pre-filled value.

        Returns:
            list[Any]: A list with one Horizontal row, ready for ``yield from``.
        """
        return [
            Horizontal(
                Label(label, classes="form-label"),
                Input(value=str(default), id=field_id, classes="form-input", type="integer"),
                classes="form-row",
            )
        ]

    def _select_row(
        self, field_id: str, label: str, options: list[str], default: str
    ) -> list[Any]:
        """Build a labelled Select row populated from a Literal's members.

        Args:
            field_id (str): DOM id matching the SetupParams field name.
            label (str): Display label.
            options (list[str]): Values to offer (display name == value).
            default (str): Preselected option.

        Returns:
            list[Any]: A list with one Horizontal row, ready for ``yield from``.
        """
        return [
            Horizontal(
                Label(label, classes="form-label"),
                Select(
                    [(opt, opt) for opt in options],
                    value=default,
                    id=field_id,
                    classes="form-input",
                    allow_blank=False,
                ),
                classes="form-row",
            )
        ]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the Start / Cancel button clicks.

        Args:
            event (Button.Pressed): The button press event.
        """
        if event.button.id == "start":
            self.action_start()
        elif event.button.id == "cancel":
            self.action_cancel()

    def action_start(self) -> None:
        """Validate the form, then push :class:`RunScreen` on success."""
        try:
            params = self._collect_params()
        except ValidationError as exc:
            self._show_error(self._format_validation_error(exc))
            return
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self._show_error("")
        self.app.push_screen(RunScreen(params=params))

    def action_cancel(self) -> None:
        """Exit the app without running anything."""
        self.app.exit(None)

    def _collect_params(self) -> SetupParams:
        """Read every form widget and build a :class:`SetupParams`.

        Returns:
            SetupParams: The validated parameter bundle.

        Raises:
            ValidationError: If any field fails Pydantic validation.
            ValueError: If any integer field cannot be parsed.
        """
        analysts: list[str] = [
            analyst
            for analyst in SUPPORTED_ANALYSTS
            if self.query_one(f"#analyst-{analyst}", Checkbox).value
        ]
        return SetupParams(
            ticker=self.query_one("#ticker", Input).value,
            date=self.query_one("#date", Input).value.strip(),
            llm_provider=self._select_value("llm_provider"),
            deep_think_llm=self.query_one("#deep_think_llm", Input).value,
            quick_think_llm=self.query_one("#quick_think_llm", Input).value,
            reasoning_effort=self._select_value("reasoning_effort"),
            response_language=self._select_value("response_language"),
            selected_analysts=analysts,
            max_debate_rounds=self._int_value("max_debate_rounds"),
            max_risk_discuss_rounds=self._int_value("max_risk_discuss_rounds"),
            max_recur_limit=self._int_value("max_recur_limit"),
            debug=self.query_one("#debug", Switch).value,
        )

    def _select_value(self, field_id: str) -> str:
        """Read a Select widget's current value, coerced to ``str``.

        Args:
            field_id (str): DOM id of the Select widget.

        Returns:
            str: The selected option's value.
        """
        return str(self.query_one(f"#{field_id}", Select).value)

    def _int_value(self, field_id: str) -> int:
        """Parse an integer Input widget's value.

        Args:
            field_id (str): DOM id of the Input widget.

        Returns:
            int: The parsed integer.

        Raises:
            ValueError: If the input is not a valid integer.
        """
        raw = self.query_one(f"#{field_id}", Input).value.strip()
        if not raw:
            raise ValueError(f"{field_id} must not be empty")
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError(f"{field_id} must be an integer, got {raw!r}") from exc

    def _show_error(self, message: str) -> None:
        """Update the inline error banner under the form.

        Args:
            message (str): Error text to display, or empty to clear.
        """
        banner = self.query_one("#setup-error", Static)
        banner.update(message)

    @staticmethod
    def _format_validation_error(exc: ValidationError) -> str:
        """Render a Pydantic ValidationError as a single-line error string.

        Args:
            exc (ValidationError): The raised validation error.

        Returns:
            str: A semicolon-separated summary of every failure.
        """
        parts: list[str] = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()))
            msg = err.get("msg", "invalid value")
            parts.append(f"{loc}: {msg}" if loc else msg)
        return "; ".join(parts)
