"""Interactive TUI runner for TradingAgents.

Wraps :func:`tradingagents.interface.cli.run_cli` with a series of
questionary prompts so a user can drive a run end-to-end without
remembering any flags. All defaults match :func:`run_cli`'s defaults so
just pressing enter reproduces the legacy python -m tradingagents.cli
behaviour.
"""

from __future__ import annotations

import sys
from typing import Any
import datetime

from rich.text import Text
from rich.panel import Panel
from rich.table import Table
import questionary
from questionary import Choice
from rich.console import Console

from tradingagents.interface.cli import DEFAULT_ANALYSTS, run_cli


class _AbortError(Exception):
    """Raised internally when a questionary prompt returns None.

    questionary signals user abort (Ctrl+C / Esc) by returning None from
    its ask() method; this exception lets us short-circuit the long
    sequence of prompts in :func:`_collect_answers` without one
    None-check per question.
    """


_LLM_PROVIDERS: tuple[str, ...] = (
    "openai",
    "anthropic",
    "google_genai",
    "xai",
    "huggingface",
    "openrouter",
    "ollama",
    "litellm",
)
_REASONING_EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
_RESPONSE_LANGUAGES: tuple[str, ...] = (
    "zh-TW",
    "zh-CN",
    "en",
    "Traditional Chinese",
    "Simplified Chinese",
    "English",
    "Japanese",
    "Korean",
)


def run_tui() -> str | None:
    """Drive a TradingAgents run via interactive questionary prompts.

    Returns:
        str | None: The final decision text returned by :func:`run_cli`,
        or None when the user cancels (Ctrl+C / aborts a prompt).
    """
    console = Console()
    console.print(
        Panel(
            Text("Interactive setup. Press Ctrl+C to abort at any time.", style="bold"),
            title="[bold cyan]TradingAgents - TUI[/]",
            title_align="left",
            border_style="cyan",
        )
    )

    try:
        answers = _collect_answers()
    except _AbortError:
        console.print("[yellow]Aborted.[/]")
        return None

    _print_summary(console, answers)

    try:
        confirmed = _ask(questionary.confirm("Start run with these settings?", default=True))
    except _AbortError:
        console.print("[yellow]Aborted.[/]")
        return None
    if not confirmed:
        console.print("[yellow]Aborted.[/]")
        return None

    return run_cli(**answers)


def _collect_answers() -> dict[str, Any]:
    """Collect every run_cli parameter via questionary prompts.

    Returns:
        dict[str, Any]: Keyword arguments suitable for :func:`run_cli`.

    Raises:
        _AbortError: When the user cancels any prompt.
    """
    today = datetime.date.today().strftime("%Y-%m-%d")

    ticker = _ask(questionary.text("Ticker symbol", default="GOOG")).strip() or "GOOG"
    date = _ask(
        questionary.text("Trade date (YYYY-MM-DD)", default=today, validate=_validate_date)
    )
    llm_provider = _ask(
        questionary.select("LLM provider", choices=list(_LLM_PROVIDERS), default="google_genai")
    )
    deep_think_llm = _ask(
        questionary.text(
            "Deep-thinking LLM (Research Manager / Risk Manager)", default="gemini-3.1-pro-preview"
        )
    )
    quick_think_llm = _ask(
        questionary.text(
            "Quick-thinking LLM (analysts / researchers / trader)",
            default="gemini-3-flash-preview",
        )
    )
    reasoning_effort = _ask(
        questionary.select("Reasoning effort", choices=list(_REASONING_EFFORTS), default="high")
    )
    response_language = _ask(
        questionary.select("Response language", choices=list(_RESPONSE_LANGUAGES), default="zh-TW")
    )
    selected_analysts = _ask(
        questionary.checkbox(
            "Select analysts to include",
            choices=[Choice(name, checked=True) for name in DEFAULT_ANALYSTS],
        )
    ) or list(DEFAULT_ANALYSTS)

    max_debate_rounds = _ask_int("Max Bull/Bear debate rounds", default=10)
    max_risk_discuss_rounds = _ask_int("Max risk-management debate rounds", default=10)
    max_recur_limit = _ask_int("Max recursion limit (must be >= 25)", default=100, minimum=25)
    debug = _ask(questionary.confirm("Stream agent messages (debug mode)?", default=True))

    return {
        "ticker": ticker,
        "date": date,
        "llm_provider": llm_provider,
        "deep_think_llm": deep_think_llm,
        "quick_think_llm": quick_think_llm,
        "reasoning_effort": reasoning_effort,
        "response_language": response_language,
        "max_debate_rounds": max_debate_rounds,
        "max_risk_discuss_rounds": max_risk_discuss_rounds,
        "max_recur_limit": max_recur_limit,
        "selected_analysts": selected_analysts,
        "debug": debug,
    }


def _ask(question: questionary.Question) -> Any:  # noqa: ANN401
    """Run a questionary prompt, converting a None abort into _AbortError.

    Args:
        question (questionary.Question): A constructed questionary prompt.

    Returns:
        Any: Whatever the prompt yields (str / list / bool depending on
        the prompt type).

    Raises:
        _AbortError: If the user cancels the prompt.
    """
    answer = question.ask()
    if answer is None:
        raise _AbortError
    return answer


def _ask_int(message: str, *, default: int, minimum: int = 0) -> int:
    """Prompt for an integer value with validation.

    Args:
        message (str): The questionary prompt label.
        default (int): The default value pre-filled into the prompt.
        minimum (int, optional): Minimum allowed value (inclusive).
            Defaults to 0.

    Returns:
        int: The parsed integer.

    Raises:
        _AbortError: If the user cancels the prompt.
    """

    def _validate(value: str) -> bool | str:
        try:
            parsed = int(value)
        except ValueError:
            return "Please enter an integer."
        if parsed < minimum:
            return f"Must be >= {minimum}."
        return True

    raw = _ask(questionary.text(message, default=str(default), validate=_validate))
    return int(raw)


def _validate_date(value: str) -> bool | str:
    """Validate that the input parses as YYYY-MM-DD.

    Args:
        value (str): The user-entered date string.

    Returns:
        bool | str: True on success, otherwise an error message string
        consumed by questionary.
    """
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return "Use YYYY-MM-DD format."
    return True


def _print_summary(console: Console, answers: dict[str, Any]) -> None:
    """Print a Rich summary table of the collected answers.

    Args:
        console (Console): The Rich console to print on.
        answers (dict[str, Any]): The keyword arguments collected by
            :func:`_collect_answers`.
    """
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    for key, value in answers.items():
        value_str = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
        table.add_row(key, value_str)
    console.print(
        Panel(
            table, title="[bold]Configured Run[/]", title_align="left", border_style="bright_blue"
        )
    )


if __name__ == "__main__":
    sys.exit(0 if run_tui() is not None else 1)
