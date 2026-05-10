"""Post-trade reflection runner for the ``tradingagents reflect`` CLI."""

from __future__ import annotations

import re
import json
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.console import Console

from tradingagents.llm import LLMProvider, ReasoningEffort  # noqa: TC001
from tradingagents.config import ResponseLanguage, TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.agents.utils.agent_states import AgentState, RiskDebateState, InvestDebateState

if TYPE_CHECKING:
    from pathlib import Path

_SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_path_component(value: str) -> str:
    """Replicate :func:`tradingagents.graph.trading_graph._safe_path_component`.

    Kept local so this module does not depend on the graph implementation
    detail solely for filename normalisation.
    """
    safe = _SAFE_PATH_RE.sub("_", value.strip()).strip("._")
    return safe or "unknown"


def _resolve_state_log(results_dir: Path, ticker: str, date: str) -> tuple[Path, dict]:
    """Locate and parse the previously-written state log for ``(ticker, date)``."""
    ticker_safe = _safe_path_component(ticker)
    log_path = results_dir / ticker_safe / f"full_states_log_{ticker_safe}_{date}.json"
    if not log_path.exists():
        raise FileNotFoundError(
            f"No state log at {log_path}. Run `tradingagents cli --ticker {ticker} "
            f"--date {date}` first."
        )
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    if date not in payload:
        raise KeyError(
            f"date {date!r} not found in {log_path}. Available keys: {sorted(payload.keys())}"
        )
    return log_path, payload[date]


def _reconstruct_state(raw: dict, ticker: str, date: str) -> AgentState:
    """Rebuild an :class:`AgentState` from the dict shape that ``_log_state`` writes."""
    invest_kwargs = raw.get("investment_debate_state") or {}
    risk_kwargs = raw.get("risk_debate_state") or {}
    return AgentState(
        company_of_interest=raw.get("company_of_interest") or ticker,
        trade_date=raw.get("trade_date") or date,
        market_report=raw.get("market_report", ""),
        sentiment_report=raw.get("sentiment_report", ""),
        news_report=raw.get("news_report", ""),
        fundamentals_report=raw.get("fundamentals_report", ""),
        investment_debate_state=InvestDebateState(**invest_kwargs),
        investment_plan=raw.get("investment_plan", ""),
        trader_investment_plan=raw.get("trader_investment_decision", ""),
        risk_debate_state=RiskDebateState(**risk_kwargs),
        final_trade_decision=raw.get("final_trade_decision", ""),
    )


def run_reflect(  # noqa: PLR0913
    ticker: str,
    date: str,
    returns: float,
    llm_provider: LLMProvider = "google_genai",
    deep_think_llm: str = "gemini-3.1-pro-preview",
    quick_think_llm: str = "gemini-3-flash-preview",
    reasoning_effort: ReasoningEffort = "high",
    response_language: ResponseLanguage = "zh-TW",
    max_debate_rounds: int = 10,
    max_risk_discuss_rounds: int = 10,
    max_recur_limit: int = 100,
) -> None:
    """Reflect on a previously-recorded run and update institutional memory.

    Reads ``full_states_log_<TICKER>_<DATE>.json`` written by a prior
    ``tradingagents cli`` run, reconstructs the AgentState, runs the
    Reflector across each of the five agent components, and persists the
    lessons to ``<data_cache_dir>/memories/*.jsonl`` so future runs surface
    them via BM25 retrieval.

    The Reflector grades reasoning quality, not just outcomes — honest
    negative ``returns`` inputs are useful even when the original reasoning
    correctly priced in the risk that materialised.

    Args:
        ticker (str): Ticker symbol that was previously analysed.
        date (str): Trade date in YYYY-MM-DD format. Must match the date
            the original ``cli`` run used.
        returns (float): Realised P/L for the trade as a fraction (e.g.
            0.025 for +2.5 %, -0.04 for -4 %).
        llm_provider (LLMProvider, optional): LangChain init_chat_model
            registry key. Should match the provider used for the original
            run for consistent reflection style. Defaults to google_genai.
        deep_think_llm (str, optional): Deep-thinking model identifier.
            Defaults to gemini-3.1-pro-preview.
        quick_think_llm (str, optional): Quick-thinking model identifier
            (this is the reflector's LLM). Defaults to gemini-3-flash-preview.
        reasoning_effort (ReasoningEffort, optional): Unified reasoning
            level. Defaults to high.
        response_language (ResponseLanguage, optional): BCP 47 language
            tag appended to the reflector prompt. Defaults to zh-TW.
        max_debate_rounds (int, optional): Mirror of the original
            TradingAgentsConfig field; not used during reflection but
            required by the config. Defaults to 10.
        max_risk_discuss_rounds (int, optional): Same. Defaults to 10.
        max_recur_limit (int, optional): Same. Defaults to 100.
    """
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

    log_path, raw = _resolve_state_log(config.results_dir, ticker, date)
    state = _reconstruct_state(raw, ticker, date)

    console = Console()
    console.print(
        Panel(
            f"Reflecting on [bold]{ticker}[/] @ [bold]{date}[/]\n"
            f"Returns: [bold]{returns:+.4f}[/]\n"
            f"State source: {log_path}",
            title="[bold cyan]Post-trade reflection[/]",
            border_style="cyan",
        )
    )

    ta = TradingAgentsGraph(config=config)
    ta.reflect_and_remember(returns, state=state)

    memories_dir = config.data_cache_dir / "memories"
    console.print(f"[green]Memory updated:[/] {memories_dir}")
