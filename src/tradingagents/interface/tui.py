"""Interactive TUI runner powered by `questionary`.

This module exposes :func:`run_tui`, which collects every value of
:class:`TradingAgentsConfig` (plus the graph-level ticker, trade date, debug
flag, and selected analysts) through a series of `questionary` prompts and
then executes the trading graph.

UX policy:
    Text and checkbox prompts intentionally do not pre-fill or pre-check the
    input. The default is shown via the prompt's ``instruction`` slot, and an
    empty answer (just pressing Enter) falls back to that default. Anything
    the user types or ticks fully overrides the default.

    ``select`` prompts must always have a highlighted option, so the default
    stays pre-highlighted but is also surfaced in the instruction.
    ``confirm`` keeps the standard Y/n / y/N convention.
"""

from typing import cast, get_args
from pathlib import Path
import datetime
from dataclasses import dataclass
from collections.abc import Callable

import questionary
from questionary import Choice, Validator, ValidationError

from tradingagents.llm import LLMProvider, ReasoningEffort
from tradingagents.config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph

from .display import console, print_header, print_summary, print_decision

_PROVIDER_CHOICES: tuple[str, ...] = get_args(LLMProvider)
_REASONING_CHOICES: tuple[str, ...] = get_args(ReasoningEffort)
_ANALYST_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("market", "Market Analyst (technical indicators, OHLCV)"),
    ("social", "Social Media Analyst (Reddit, X sentiment)"),
    ("news", "News Analyst (global news + insider tx)"),
    ("fundamentals", "Fundamentals Analyst (financial statements)"),
)

_DEFAULT_TICKER: str = "2330"
_DEFAULT_LLM_PROVIDER: LLMProvider = "google_genai"
_DEFAULT_DEEP_THINK_LLM: str = "gemini-3.1-pro-preview"
_DEFAULT_QUICK_THINK_LLM: str = "gemini-3-flash-preview"
_DEFAULT_REASONING_EFFORT: ReasoningEffort = "high"
_DEFAULT_RESPONSE_LANGUAGE: str = "zh-TW"
_DEFAULT_MAX_DEBATE_ROUNDS: int = 10
_DEFAULT_MAX_RISK_DISCUSS_ROUNDS: int = 10
_DEFAULT_MAX_RECUR_LIMIT: int = 100
_DEFAULT_RESULTS_DIR: str = "./results"
_DEFAULT_DEBUG: bool = True


@dataclass(frozen=True)
class _RunAnswers:
    """Strongly-typed snapshot of the answers collected by the TUI."""

    ticker: str
    trade_date: str
    llm_provider: LLMProvider
    deep_think_llm: str
    quick_think_llm: str
    reasoning_effort: ReasoningEffort
    response_language: str
    selected_analysts: list[str]
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    max_recur_limit: int
    results_dir: str
    debug: bool

    def to_summary_rows(self) -> list[tuple[str, str]]:
        """Render this answer set as ``(field, value)`` pairs for Rich tables.

        Returns:
            list[tuple[str, str]]: Ordered rows for ``display.print_summary``.
        """
        return [
            ("ticker", self.ticker),
            ("trade_date", self.trade_date),
            ("llm_provider", self.llm_provider),
            ("deep_think_llm", self.deep_think_llm),
            ("quick_think_llm", self.quick_think_llm),
            ("reasoning_effort", self.reasoning_effort),
            ("response_language", self.response_language),
            ("selected_analysts", ", ".join(self.selected_analysts)),
            ("max_debate_rounds", str(self.max_debate_rounds)),
            ("max_risk_discuss_rounds", str(self.max_risk_discuss_rounds)),
            ("max_recur_limit", str(self.max_recur_limit)),
            ("results_dir", self.results_dir),
            ("debug", str(self.debug)),
        ]


class _DateValidator(Validator):
    """Validate the answer is a `YYYY-MM-DD` date string, or empty for default."""

    def validate(self, document: object) -> None:
        """Raise :class:`ValidationError` if a non-empty input is not a valid date.

        An empty input is intentionally allowed: the caller interprets it as
        "use the default" and falls back to the default value.

        Args:
            document (object): The questionary document whose ``text``
                attribute holds the current input.

        Raises:
            ValidationError: If the input is non-empty and does not parse as
                ``YYYY-MM-DD``.
        """
        text = str(getattr(document, "text", "")).strip()
        if not text:
            return
        try:
            datetime.date.fromisoformat(text)
        except ValueError as exc:
            raise ValidationError(
                message="Date must be in YYYY-MM-DD format", cursor_position=len(text)
            ) from exc


class _PositiveIntValidator(Validator):
    """Validate the answer is a positive integer above ``minimum``, or empty for default."""

    def __init__(self, minimum: int = 1) -> None:
        """Create a validator with a configurable lower bound.

        Args:
            minimum (int, optional): Smallest allowed value. Defaults to 1.
        """
        self._minimum = minimum

    def validate(self, document: object) -> None:
        """Raise :class:`ValidationError` if a non-empty input is not a valid integer.

        An empty input is intentionally allowed: the caller interprets it as
        "use the default" and falls back to the default value.

        Args:
            document (object): The questionary document object.

        Raises:
            ValidationError: If the input is non-empty and either does not
                parse as an integer or is below the configured minimum.
        """
        text = str(getattr(document, "text", "")).strip()
        if not text:
            return
        try:
            value = int(text)
        except ValueError as exc:
            raise ValidationError(
                message="Please enter an integer", cursor_position=len(text)
            ) from exc
        if value < self._minimum:
            raise ValidationError(
                message=f"Value must be >= {self._minimum}", cursor_position=len(text)
            )


def _abort(label: str) -> None:
    """Abort the TUI flow when a prompt returns ``None``.

    Args:
        label (str): The label of the prompt the user cancelled.

    Raises:
        SystemExit: Always; uses code 130 (SIGINT-like) so shells can detect cancellation.
    """
    console.print(f"[yellow]Aborted at:[/yellow] {label}")
    raise SystemExit(130)


def _ask_text(
    prompt: str,
    *,
    default: str,
    label: str,
    validate: Validator | Callable[[str], bool | str] | None = None,
) -> str:
    """Ask a single-line text question; empty answer falls back to ``default``.

    The input box is intentionally blank — the default is surfaced via
    ``instruction`` so the user is never silently typing on top of a
    pre-filled value. The validator passed in must permit an empty string
    (treated as "use default"); the helper then applies the fallback.

    Args:
        prompt (str): The prompt shown to the user.
        default (str): Value used when the user submits an empty answer.
        label (str): Label used in the abort message.
        validate (Validator | Callable[[str], bool | str] | None, optional):
            Questionary validator that must permit empty input. Defaults to None.

    Returns:
        str: The user's trimmed answer, or ``default`` when the answer is empty.
    """
    answer = questionary.text(
        prompt, instruction=f"(default: {default}) ", validate=validate
    ).ask()
    if answer is None:
        _abort(label)
    answer = str(answer).strip()
    return answer if answer else default


def _ask_select(prompt: str, *, choices: list[str], default: str, label: str) -> str:
    """Ask a single-choice select question.

    questionary's ``select`` always keeps one option highlighted, so the
    default stays pre-highlighted but is also echoed in the ``instruction``
    slot for transparency. Pressing Enter without arrow-keying selects the
    highlighted default.

    Args:
        prompt (str): The prompt shown to the user.
        choices (list[str]): List of selectable string options.
        default (str): The pre-highlighted default.
        label (str): Label used in the abort message.

    Returns:
        str: The chosen option.
    """
    answer = questionary.select(
        prompt, choices=choices, default=default, instruction=f"(default: {default})"
    ).ask()
    if answer is None:
        _abort(label)
    return str(answer)


def _ask_checkbox(
    prompt: str, *, choices: list[tuple[str, str]], default: list[str], label: str
) -> list[str]:
    """Ask a multi-select checkbox question; empty selection falls back to ``default``.

    No items are pre-checked. The default set is shown via ``instruction``;
    submitting with nothing ticked keeps that default. Any explicit selection
    overrides the default entirely.

    Args:
        prompt (str): The prompt shown to the user.
        choices (list[tuple[str, str]]): ``(value, description)`` pairs to render.
        default (list[str]): Values used when nothing is ticked.
        label (str): Label used in the abort message.

    Returns:
        list[str]: Selected values, or ``default`` when nothing was ticked.
    """
    width = max((len(key) for key, _ in choices), default=0)
    qchoices = [
        Choice(title=f"{key:<{width}} - {desc}", value=key, checked=False) for key, desc in choices
    ]
    answer = questionary.checkbox(
        prompt,
        choices=qchoices,
        instruction=f"(default: {', '.join(default)})",
        validate=lambda _values: True,
    ).ask()
    if answer is None:
        _abort(label)
    selected = [str(item) for item in answer]
    return selected if selected else list(default)


def _ask_confirm(prompt: str, *, default: bool, label: str) -> bool:
    """Ask a yes/no confirmation.

    questionary renders this as ``Y/n`` or ``y/N`` depending on ``default``,
    which is the standard convention for shell confirmations and is left
    intact (it is not a "pre-filled value" in the text-input sense).

    Args:
        prompt (str): The prompt shown to the user.
        default (bool): Default answer when the user just presses Enter.
        label (str): Label used in the abort message.

    Returns:
        bool: ``True`` for yes, ``False`` for no.
    """
    answer = questionary.confirm(prompt, default=default).ask()
    if answer is None:
        _abort(label)
    return bool(answer)


def _collect_answers() -> _RunAnswers:
    """Drive the questionary flow and return a typed :class:`_RunAnswers`.

    Returns:
        _RunAnswers: Fully populated answers ready to be split between
        :class:`TradingAgentsConfig` and :class:`TradingAgentsGraph`.

    Raises:
        SystemExit: If the user aborts any individual prompt.
    """
    today = datetime.date.today().strftime("%Y-%m-%d")

    ticker = _ask_text("Stock ticker:", default=_DEFAULT_TICKER, label="ticker")
    trade_date = _ask_text(
        "Trade date (YYYY-MM-DD):", default=today, validate=_DateValidator(), label="trade_date"
    )

    llm_provider = cast(
        "LLMProvider",
        _ask_select(
            "LLM provider:",
            choices=list(_PROVIDER_CHOICES),
            default=_DEFAULT_LLM_PROVIDER,
            label="llm_provider",
        ),
    )
    deep_think_llm = _ask_text(
        "Deep-thinking model (Research/Risk Manager):",
        default=_DEFAULT_DEEP_THINK_LLM,
        label="deep_think_llm",
    )
    quick_think_llm = _ask_text(
        "Quick-thinking model (analysts, debators):",
        default=_DEFAULT_QUICK_THINK_LLM,
        label="quick_think_llm",
    )
    reasoning_effort = cast(
        "ReasoningEffort",
        _ask_select(
            "Reasoning effort:",
            choices=list(_REASONING_CHOICES),
            default=_DEFAULT_REASONING_EFFORT,
            label="reasoning_effort",
        ),
    )
    response_language = _ask_text(
        "Response language (e.g. en, zh-TW, Japanese):",
        default=_DEFAULT_RESPONSE_LANGUAGE,
        label="response_language",
    )

    selected_analysts = _ask_checkbox(
        "Selected analysts (Space to toggle, Enter to confirm):",
        choices=list(_ANALYST_DEFINITIONS),
        default=[key for key, _ in _ANALYST_DEFINITIONS],
        label="selected_analysts",
    )

    max_debate_rounds = int(
        _ask_text(
            "Max Bull/Bear debate rounds:",
            default=str(_DEFAULT_MAX_DEBATE_ROUNDS),
            validate=_PositiveIntValidator(minimum=1),
            label="max_debate_rounds",
        )
    )
    max_risk_discuss_rounds = int(
        _ask_text(
            "Max risk discussion rounds:",
            default=str(_DEFAULT_MAX_RISK_DISCUSS_ROUNDS),
            validate=_PositiveIntValidator(minimum=1),
            label="max_risk_discuss_rounds",
        )
    )
    max_recur_limit = int(
        _ask_text(
            "Max LangGraph recursion limit (>= 25):",
            default=str(_DEFAULT_MAX_RECUR_LIMIT),
            validate=_PositiveIntValidator(minimum=25),
            label="max_recur_limit",
        )
    )

    results_dir = _ask_text(
        "Results directory:", default=_DEFAULT_RESULTS_DIR, label="results_dir"
    )
    debug = _ask_confirm(
        "Enable debug streaming (live message output)?", default=_DEFAULT_DEBUG, label="debug"
    )

    return _RunAnswers(
        ticker=ticker,
        trade_date=trade_date,
        llm_provider=llm_provider,
        deep_think_llm=deep_think_llm,
        quick_think_llm=quick_think_llm,
        reasoning_effort=reasoning_effort,
        response_language=response_language,
        selected_analysts=selected_analysts,
        max_debate_rounds=max_debate_rounds,
        max_risk_discuss_rounds=max_risk_discuss_rounds,
        max_recur_limit=max_recur_limit,
        results_dir=results_dir,
        debug=debug,
    )


def run_tui() -> str:
    """Run the interactive TUI end-to-end and return the final decision.

    The flow is:
        1. Print a banner.
        2. Walk the user through every configurable field.
        3. Show a Rich summary table and ask for confirmation.
        4. Build :class:`TradingAgentsGraph` and call ``propagate``.
        5. Render the final BUY/SELL/HOLD decision panel.

    Returns:
        str: The final decision string produced by the signal processor, or an
        empty string if the user cancels at the confirmation step.

    Raises:
        SystemExit: If the user aborts an individual prompt with Ctrl+C / Esc.
    """
    print_header(
        "TradingAgents · Interactive TUI", "Press Enter to keep the default value at each step."
    )

    answers = _collect_answers()
    print_summary(answers.to_summary_rows(), title="Run configuration")

    if not _ask_confirm("Proceed with this configuration?", default=True, label="confirm"):
        console.print("[yellow]Cancelled by user.[/yellow]")
        return ""

    config = TradingAgentsConfig(
        results_dir=Path(answers.results_dir),
        llm_provider=answers.llm_provider,
        deep_think_llm=answers.deep_think_llm,
        quick_think_llm=answers.quick_think_llm,
        reasoning_effort=answers.reasoning_effort,
        response_language=answers.response_language,
        max_debate_rounds=answers.max_debate_rounds,
        max_risk_discuss_rounds=answers.max_risk_discuss_rounds,
        max_recur_limit=answers.max_recur_limit,
    )
    ta = TradingAgentsGraph(
        selected_analysts=answers.selected_analysts, debug=answers.debug, config=config
    )

    _, decision = ta.propagate(answers.ticker, answers.trade_date)
    print_decision(answers.ticker, answers.trade_date, decision)
    return decision


__all__ = ["run_tui"]
