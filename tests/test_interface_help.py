from typing import Literal

from rich.console import Console

from tradingagents.interface.help import (
    _format_type,
    print_app_help,
    _format_default,
    _parse_google_args,
    print_command_help,
)


def _sample_command(ticker: str, mode: Literal["fast", "deep"] = "fast", limit: int = 3) -> None:
    """Run the sample command.

    Args:
        ticker: Ticker to analyse.
        mode: Analysis mode.
            Continued detail should be joined.
        limit: Maximum number of runs.

    Returns:
        None.
    """


def test_parse_google_args_extracts_descriptions_and_continuations() -> None:
    descriptions = _parse_google_args(_sample_command.__doc__)

    assert descriptions["ticker"] == "Ticker to analyse."
    assert descriptions["mode"] == "Analysis mode. Continued detail should be joined."
    assert descriptions["limit"] == "Maximum number of runs."


def test_format_type_and_default_render_terminal_friendly_values() -> None:
    assert _format_type(Literal["fast", "deep"]) == "'fast' | 'deep'"
    assert _format_type(str) == "str"
    assert _format_default("fast") == "'fast'"


def test_print_command_help_renders_signature_docstring_and_examples() -> None:
    console = Console(record=True, width=120)

    print_command_help(console, "cli", _sample_command)

    output = console.export_text()
    assert "tradingagents cli" in output
    assert "Run the sample command." in output
    assert "--ticker" in output
    assert "'fast' | 'deep'" in output
    assert "Ticker to analyse." in output
    assert "tradingagents cli --ticker AAPL" in output


def test_print_app_help_renders_commands_with_docstring_summaries() -> None:
    console = Console(record=True, width=100)

    print_app_help(console, {"sample": _sample_command})

    output = console.export_text()
    assert "Multi-Agents LLM Financial Trading Framework." in output
    assert "sample" in output
    assert "Run the sample command." in output
    assert "tradingagents <command> [--flag value ...]" in output
