"""Flag-driven runner for the TradingAgents pipeline.

Exposes :func:`run_cli` as the cli subcommand of the tradingagents
console script. Each parameter is a fire-friendly flag, with defaults
matching the previous hard-coded values from the legacy cli.py.
"""

from __future__ import annotations

import datetime

from rich.console import Console

from tradingagents.llm import LLMProvider, ReasoningEffort  # noqa: TC001
from tradingagents.config import ResponseLanguage, TradingAgentsConfig
from tradingagents.graph.setup import SUPPORTED_ANALYSTS
from tradingagents.interface.display import MessageRenderer, print_run_header, print_final_decision
from tradingagents.graph.trading_graph import TradingAgentsGraph

DEFAULT_ANALYSTS: tuple[str, ...] = SUPPORTED_ANALYSTS


def _normalize_trade_date(date_value: str | None) -> str:
    """Return a validated trade date string."""
    if date_value is None:
        return datetime.date.today().strftime("%Y-%m-%d")
    try:
        parsed = datetime.date.fromisoformat(date_value)
    except ValueError as exc:
        raise ValueError(f"date must be in YYYY-MM-DD format: {date_value!r}") from exc
    today = datetime.date.today()
    if parsed > today:
        raise ValueError(f"date cannot be in the future: {date_value} > {today}")
    return parsed.strftime("%Y-%m-%d")


def _normalize_selected_analysts(
    selected_analysts: list[str] | tuple[str, ...] | None,
) -> list[str]:
    """Validate selected analyst names early for CLI/API callers."""
    analysts = list(selected_analysts) if selected_analysts else list(DEFAULT_ANALYSTS)
    normalized = []
    for analyst in analysts:
        value = str(analyst).strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    unknown = [analyst for analyst in normalized if analyst not in SUPPORTED_ANALYSTS]
    if unknown:
        raise ValueError(
            "Unknown analyst(s): "
            f"{', '.join(unknown)}. Supported analysts: {', '.join(SUPPORTED_ANALYSTS)}."
        )
    if not normalized:
        raise ValueError("At least one analyst must be selected.")
    return normalized


def run_cli(  # noqa: PLR0913
    ticker: str = "GOOG",
    date: str | None = None,
    llm_provider: LLMProvider = "google_genai",
    deep_think_llm: str = "gemini-3.1-pro-preview",
    quick_think_llm: str = "gemini-3-flash-preview",
    reasoning_effort: ReasoningEffort = "high",
    response_language: ResponseLanguage = "zh-TW",
    max_debate_rounds: int = 10,
    max_risk_discuss_rounds: int = 10,
    max_recur_limit: int = 100,
    selected_analysts: list[str] | tuple[str, ...] | None = None,
    debug: bool = True,
) -> str:
    """Run the TradingAgents pipeline for a single ticker.

    Args:
        ticker (str): Ticker symbol or company name to analyse.
            Defaults to GOOG.
        date (str | None, optional): Trade date in YYYY-MM-DD format.
            Defaults to today's local date when None.
        llm_provider (LLMProvider, optional): LangChain init_chat_model
            registry key. Defaults to google_genai.
        deep_think_llm (str, optional): Model name for deep-thinking nodes
            (Research Manager, Risk Manager). Defaults to
            gemini-3.1-pro-preview.
        quick_think_llm (str, optional): Model name for quick-thinking
            nodes (analysts, researchers, trader, debaters). Defaults to
            gemini-3-flash-preview.
        reasoning_effort (ReasoningEffort, optional): Unified reasoning
            level mapped per provider. Defaults to high.
        response_language (ResponseLanguage, optional): BCP 47 language
            tag (zh-TW, zh-CN, en-US, ja-JP, ko-KR, de-DE) appended to
            agent prompts. Defaults to zh-TW.
        max_debate_rounds (int, optional): Maximum Bull/Bear investment
            debate rounds. Defaults to 10.
        max_risk_discuss_rounds (int, optional): Maximum risk management
            debate rounds. Defaults to 10.
        max_recur_limit (int, optional): Maximum recursion limit for
            LangGraph execution. Defaults to 100.
        selected_analysts (list[str] | tuple[str, ...] | None, optional):
            Analyst types to include. Valid options are market, social,
            news, fundamentals. Defaults to all four when None.
        debug (bool, optional): Stream agent messages live (still routed
            through the Rich renderer regardless of this flag — the flag
            only affects the underlying graph's verbosity). Defaults to
            True.

    Returns:
        str: The final BUY / SELL / HOLD decision text.
    """
    date = _normalize_trade_date(date)
    analysts = _normalize_selected_analysts(selected_analysts)

    config = TradingAgentsConfig(
        llm_provider=llm_provider,
        deep_think_llm=deep_think_llm,
        quick_think_llm=quick_think_llm,
        max_debate_rounds=max_debate_rounds,
        max_risk_discuss_rounds=max_risk_discuss_rounds,
        max_recur_limit=max_recur_limit,
        reasoning_effort=reasoning_effort,
        response_language=response_language,
    )

    console = Console()
    print_run_header(console, ticker=ticker, trade_date=date, config=config)

    renderer = MessageRenderer(console=console)

    ta = TradingAgentsGraph(debug=debug, config=config, selected_analysts=analysts)
    _, decision = ta.propagate(ticker, date, on_message=renderer)

    print_final_decision(console, decision)
    return decision
