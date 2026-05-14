"""Backtest harness for TradingAgents.

Drives :meth:`TradingAgentsGraph.propagate` across a date grid for one or
more tickers, captures the structured :class:`TradeRecommendation` at
each decision date, scores the realised return against the next-bar
price action, and aggregates Sharpe / hit rate / expectancy / drawdown.

The harness is the gating piece for P2 evaluation: any prompt or tool
change after P1 must move these metrics in the right direction to land,
otherwise it is undoing the work of an earlier change.

Two modes:

- **Real run** drives the live ``TradingAgentsGraph`` for each
  (ticker, decision_date) and accumulates LLM cost via
  :class:`CostTracker`. The loop halts when ``budget_cap_usd`` is hit.
- **Dry run** swaps in :class:`StubChatModel` so the harness itself can
  be validated in seconds without burning API budget. The stub always
  produces a parseable Risk Judge JSON + canonical line.

Per-trade reflection is optional (``reflect_after_each_trade=True``):
the realised return is fed back through
:meth:`TradingAgentsGraph.reflect_and_remember` so memory grows during
the backtest just as it would in production.
"""

from __future__ import annotations

import math
from typing import Any, Literal
import logging
from datetime import datetime, timedelta
from collections.abc import Callable  # noqa: TC003  # runtime needed for Backtester.run signature

import pandas as pd
from pydantic import Field, BaseModel, ConfigDict, SkipValidation
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel

from tradingagents.config import (
    TradingAgentsConfig,  # noqa: TC001  # Pydantic field annotation needs runtime resolution
)
from tradingagents.dataflows.yfinance import _resolve_history_with_cache
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.signal_processing import TradeRecommendation

logger = logging.getLogger(__name__)

Frequency = Literal["daily", "weekly"]

# Approximate per-million-token costs in USD. The exact numbers move
# constantly; this table is intentionally conservative so the budget
# cap fires slightly early rather than overruns silently. Unknown
# models fall through to (0, 0) which disables cost enforcement for
# that call but still counts tokens.
_PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    # (input, output) per 1,000,000 tokens
    "gemini-flash-latest": (0.075, 0.30),
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-3-flash-preview": (0.10, 0.40),
    "gemini-pro-latest": (1.25, 5.00),
    "gemini-3.1-pro-preview": (2.50, 10.00),
    "gpt-5-mini": (0.50, 4.00),
    "gpt-5": (5.00, 25.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
}


class CostBudgetExceeded(RuntimeError):  # noqa: N818 -- public API name, kept stable
    """Raised when cumulative LLM spend exceeds ``budget_cap_usd``."""


class BacktestConfig(BaseModel):
    """User-facing knobs for a backtest run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tickers: list[str] = Field(
        ..., title="Tickers", description="Ticker symbols to evaluate in this backtest."
    )
    start_date: str = Field(
        ...,
        title="Start Date",
        description="Inclusive lower bound of the decision-date grid (YYYY-MM-DD).",
    )
    end_date: str = Field(
        ...,
        title="End Date",
        description="Inclusive upper bound of the decision-date grid (YYYY-MM-DD).",
    )
    frequency: Frequency = Field(
        default="weekly",
        title="Frequency",
        description=(
            "How densely the decision-date grid is sampled. 'daily' uses every "
            "business day; 'weekly' resamples to Fridays."
        ),
    )
    horizon_days: int = Field(
        default=5,
        ge=1,
        title="Horizon (days)",
        description=(
            "Number of trading bars forward used to compute realised return. "
            "A BUY entered at decision_date is marked-to-market at "
            "decision_date + horizon_days bars."
        ),
    )
    initial_cash: float = Field(
        default=100_000.0,
        gt=0,
        title="Initial Cash",
        description="Notional cash used for hit-rate / drawdown reporting; the "
        "harness does not maintain a running portfolio.",
    )
    max_position_fraction: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        title="Max Position Fraction",
        description=(
            "Upper bound applied to the LLM-provided size_fraction before computing "
            "realised return; safer than trusting the LLM not to size at 1.0."
        ),
    )
    budget_cap_usd: float | None = Field(
        default=None,
        ge=0,
        title="Budget Cap (USD)",
        description=(
            "Stop the run when the CostTracker-estimated cumulative LLM spend "
            "exceeds this many USD. None disables enforcement."
        ),
    )
    dry_run: bool = Field(
        default=False,
        title="Dry Run",
        description=(
            "Use StubChatModel instead of real LLM calls so the harness can be "
            "validated against mock OHLCV in seconds."
        ),
    )
    reflect_after_each_trade: bool = Field(
        default=True,
        title="Reflect After Each Trade",
        description=(
            "When True, calls TradingAgentsGraph.reflect_and_remember after each "
            "decision so memory grows just as it would in production."
        ),
    )
    trading_config: TradingAgentsConfig = Field(
        ...,
        title="Trading Config",
        description=(
            "The TradingAgentsConfig that backs every TradingAgentsGraph "
            "instance the backtest constructs."
        ),
    )


class TradeRecord(BaseModel):
    """One (ticker, decision_date) outcome row."""

    ticker: str
    decision_date: str
    recommendation: TradeRecommendation
    entry_price: float | None = None
    exit_date: str | None = None
    exit_price: float | None = None
    realised_return: float = 0.0
    notes: str = ""


class BacktestReport(BaseModel):
    """Aggregate metrics + per-trade detail returned by :meth:`Backtester.run`."""

    trades: list[TradeRecord]
    sharpe: float
    hit_rate: float
    expectancy: float
    avg_trade_return: float
    worst_drawdown: float
    total_return: float
    n_buy: int
    n_sell: int
    n_hold: int
    estimated_cost_usd: float


class CostTracker(BaseCallbackHandler):
    """Best-effort LLM cost tracker; tallies tokens via callback events.

    LangChain providers populate ``ChatResult.llm_output["token_usage"]``
    on completion. This handler reads that, multiplies by the pricing
    table, and raises :class:`CostBudgetExceeded` once the running
    total exceeds ``budget_cap_usd`` (when set). The exception is the
    cleanest way to abort an in-flight LangGraph run; the
    :meth:`Backtester.run` loop catches it and stops cleanly.
    """

    def __init__(self, budget_cap_usd: float | None = None) -> None:
        super().__init__()
        self.budget_cap_usd = budget_cap_usd
        self.total_cost_usd = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Update token + cost totals from one finished LLM call."""
        self.calls += 1
        usage = _extract_token_usage(response)
        if usage is None:
            return
        input_tok, output_tok, model_name = usage
        self.input_tokens += input_tok
        self.output_tokens += output_tok
        price_in, price_out = _PRICING_USD_PER_MTOK.get(model_name, (0.0, 0.0))
        cost = (input_tok * price_in + output_tok * price_out) / 1_000_000.0
        self.total_cost_usd += cost
        if self.budget_cap_usd is not None and self.total_cost_usd > self.budget_cap_usd:
            raise CostBudgetExceeded(
                f"Cumulative LLM spend {self.total_cost_usd:.4f} USD exceeded cap "
                f"{self.budget_cap_usd:.4f} USD after {self.calls} call(s)."
            )


def _extract_token_usage(response: Any) -> tuple[int, int, str] | None:  # noqa: ANN401
    """Pull ``(input_tokens, output_tokens, model_name)`` out of an LLM response."""
    llm_output = getattr(response, "llm_output", None) or {}
    model_name = ""
    if isinstance(llm_output, dict):
        model_name = str(
            llm_output.get("model_name")
            or llm_output.get("model")
            or llm_output.get("model_id")
            or ""
        )
        usage = llm_output.get("token_usage") or llm_output.get("usage")
        if isinstance(usage, dict):
            input_tok = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            output_tok = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            if input_tok or output_tok:
                return input_tok, output_tok, model_name
    # Fall back to the per-generation usage_metadata that newer LangChain
    # versions expose via ``AIMessage.usage_metadata``.
    generations = getattr(response, "generations", None) or []
    for gen_list in generations:
        for gen in gen_list:
            msg = getattr(gen, "message", None)
            usage = getattr(msg, "usage_metadata", None) if msg is not None else None
            if isinstance(usage, dict):
                input_tok = int(usage.get("input_tokens") or 0)
                output_tok = int(usage.get("output_tokens") or 0)
                if input_tok or output_tok:
                    return input_tok, output_tok, model_name
    return None


_STUB_RISK_JUDGE_TEMPLATE = """Stub risk-judge response (dry_run).

```json
{{
  "signal": "{signal}",
  "size_fraction": 0.5,
  "target_price": null,
  "stop_loss": null,
  "time_horizon_days": 5,
  "confidence": 0.6,
  "rationale": "Stub rationale for backtest harness validation.",
  "warning_message": null
}}
```

FINAL TRANSACTION PROPOSAL: **{signal}**
"""


def _stub_canned_response(prompt_text: str) -> str:
    """Return a parseable stub response keyed on the calling node's prompt content."""
    lowered = prompt_text.lower()
    # Risk Manager prompt mentions "risk management judge" + the JSON schema
    if "risk management judge" in lowered or "structured recommendation" in lowered:
        return _STUB_RISK_JUDGE_TEMPLATE.format(signal="BUY")
    # Trader prompt mentions "trader"
    if "you are the trader" in lowered:
        return (
            "Stub trader plan. Will follow the manager's BUY plan with 0.5 sizing.\n\n"
            "FINAL TRANSACTION PROPOSAL: **BUY**"
        )
    # Research Manager prompt
    if "portfolio manager" in lowered or "### recommendation:" in lowered:
        return (
            "### Recommendation: BUY\n"
            "Rationale: stub manager rationale.\n"
            "Strategic Actions: stub action list."
        )
    # Situation Summariser
    if "situation summariser" in lowered or "ticker profile" in lowered:
        return (
            "### Ticker profile\n- stub ticker, mid-cap, USD.\n"
            "### Price action and regime\n- trend: up; volatility: normal.\n"
            "### Indicator polarity\n- bullish (stub RSI 55, MACD positive).\n"
            "### Catalysts and news\n- stub catalyst.\n"
            "### Sentiment polarity\n- neutral, no divergence.\n"
            "### Fundamental health\n- mixed.\n"
            "### Key risks\n- stub risk.\n"
        )
    # Bull / Bear / debaters / analysts — produce neutral prose
    return "Stub analyst / debater output (dry_run). Tools are skipped in dry_run mode."


class StubChatModel(BaseChatModel):
    """In-memory chat-model stub used by ``BacktestConfig.dry_run=True``.

    Implements :class:`BaseChatModel` minimally so it slots into every
    place a real provider does, including ``llm.bind_tools(...)``. Tool
    calls are deliberately never produced so analyst loops short-circuit
    to a single response per analyst.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:  # pragma: no cover -- LangChain hook
        return "stub-chat-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401  # LangChain interface
    ) -> ChatResult:
        prompt_text = "\n".join(str(getattr(m, "content", "") or "") for m in messages)
        content = _stub_canned_response(prompt_text)
        message = AIMessage(content=content)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(
        self,
        tools: Any,  # noqa: ANN401  # langchain passes a list of tools, schemas, or callables
        **kwargs: Any,  # noqa: ANN401
    ) -> StubChatModel:
        """Ignore the tool list -- stub responses never contain tool_calls."""
        _ = (tools, kwargs)
        return self


def _decision_grid(start_date: str, end_date: str, frequency: Frequency) -> list[str]:
    """Return decision-date strings (YYYY-MM-DD) inside ``[start_date, end_date]``."""
    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date)
    if start_dt > end_dt:
        raise ValueError(f"start_date must be on or before end_date: {start_date} > {end_date}")
    if frequency == "weekly":
        # Resample business days to weekly Fridays inside the window.
        weekly = pd.bdate_range(start=start_dt, end=end_dt, freq="W-FRI")
        if weekly.empty:
            weekly = pd.bdate_range(start=start_dt, end=end_dt)
        dates = weekly
    else:
        dates = pd.bdate_range(start=start_dt, end=end_dt)
    return [d.strftime("%Y-%m-%d") for d in dates]


def _exit_price_after_horizon(
    history: pd.DataFrame, decision_date: str, horizon_days: int
) -> tuple[str | None, float | None]:
    """Return ``(exit_date, exit_close)`` ``horizon_days`` bars after decision."""
    if history.empty or "Date" not in history.columns or "Close" not in history.columns:
        return None, None
    dates = pd.to_datetime(history["Date"])
    decision_ts = pd.Timestamp(decision_date)
    future_mask = dates > decision_ts
    future = history.loc[future_mask].reset_index(drop=True)
    if future.empty:
        return None, None
    target_idx = min(horizon_days - 1, len(future) - 1)
    row = future.iloc[target_idx]
    return pd.Timestamp(row["Date"]).strftime("%Y-%m-%d"), float(row["Close"])


def _entry_price_on(history: pd.DataFrame, decision_date: str) -> tuple[str | None, float | None]:
    """Return ``(entry_date, entry_close)`` for the first trading bar >= decision_date.

    Trades enter on the close of the decision date (or the next open trading day
    if decision_date itself is not a trading day -- weekend / holiday).
    """
    if history.empty or "Date" not in history.columns or "Close" not in history.columns:
        return None, None
    dates = pd.to_datetime(history["Date"])
    decision_ts = pd.Timestamp(decision_date)
    eligible = history.loc[dates >= decision_ts].reset_index(drop=True)
    if eligible.empty:
        return None, None
    row = eligible.iloc[0]
    return pd.Timestamp(row["Date"]).strftime("%Y-%m-%d"), float(row["Close"])


def _signed_return(
    signal: str, entry: float, exit_close: float, size_fraction: float, cap: float
) -> float:
    """Convert (signal, entry, exit, size) into a signed realised return."""
    raw = (exit_close / entry - 1.0) if entry > 0 else 0.0
    size = max(0.0, min(size_fraction, cap))
    if signal == "BUY":
        return raw * size
    if signal == "SELL":
        return -raw * size
    return 0.0


def _periods_per_year(frequency: Frequency) -> float:
    return 252.0 if frequency == "daily" else 52.0


def _aggregate_report(
    trades: list[TradeRecord], frequency: Frequency, cost_usd: float
) -> BacktestReport:
    """Compute the summary metrics over ``trades``."""
    if not trades:
        return BacktestReport(
            trades=[],
            sharpe=float("nan"),
            hit_rate=float("nan"),
            expectancy=0.0,
            avg_trade_return=0.0,
            worst_drawdown=0.0,
            total_return=0.0,
            n_buy=0,
            n_sell=0,
            n_hold=0,
            estimated_cost_usd=cost_usd,
        )

    returns = [t.realised_return for t in trades]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / max(len(returns) - 1, 1)
    stdev = math.sqrt(variance) if variance > 0 else 0.0
    periods = _periods_per_year(frequency)
    sharpe = (mean / stdev) * math.sqrt(periods) if stdev > 0 else float("nan")

    profitable = [r for r in returns if r > 0]
    losing = [r for r in returns if r < 0]
    hit_rate = len(profitable) / len(returns) if returns else float("nan")
    avg_win = sum(profitable) / len(profitable) if profitable else 0.0
    avg_loss = sum(losing) / len(losing) if losing else 0.0
    expectancy = hit_rate * avg_win + (1 - hit_rate) * avg_loss

    # Worst drawdown is the maximum peak-to-trough decline of the
    # cumulative compounded return series.
    cumulative = 1.0
    peak = 1.0
    worst_dd = 0.0
    for r in returns:
        cumulative *= 1.0 + r
        peak = max(peak, cumulative)
        if peak > 0:
            worst_dd = min(worst_dd, cumulative / peak - 1.0)

    return BacktestReport(
        trades=trades,
        sharpe=sharpe,
        hit_rate=hit_rate,
        expectancy=expectancy,
        avg_trade_return=mean,
        worst_drawdown=worst_dd,
        total_return=cumulative - 1.0,
        n_buy=sum(1 for t in trades if t.recommendation.signal == "BUY"),
        n_sell=sum(1 for t in trades if t.recommendation.signal == "SELL"),
        n_hold=sum(1 for t in trades if t.recommendation.signal == "HOLD"),
        estimated_cost_usd=cost_usd,
    )


class Backtester(BaseModel):
    """Drives :meth:`TradingAgentsGraph.propagate` across a date grid."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    config: BacktestConfig = Field(..., title="Config", description="Backtest configuration.")
    _stub_singleton: SkipValidation[StubChatModel | None] = None

    def _maybe_install_stub_llm(self) -> Callable[[], None] | None:
        """Monkeypatch ``build_chat_model`` to the stub when ``dry_run`` is True.

        Returns a teardown callable that restores the real factory. Done
        in-process via attribute replacement on the two import sites that
        actually look up ``build_chat_model`` at runtime.
        """
        if not self.config.dry_run:
            return None

        stub = StubChatModel()
        self._stub_singleton = stub

        from tradingagents import llm as llm_module  # noqa: PLC0415 -- patched at runtime
        from tradingagents.graph import trading_graph as trading_graph_module  # noqa: PLC0415

        originals: list[tuple[Any, str, Any]] = []
        for module in (llm_module, trading_graph_module):
            attr = "build_chat_model"
            if hasattr(module, attr):
                originals.append((module, attr, getattr(module, attr)))
                setattr(module, attr, lambda *_a, **_kw: stub)

        def restore() -> None:
            for module, attr, original in originals:
                setattr(module, attr, original)

        return restore

    def run(  # noqa: C901 -- the loop is one cohesive workflow; splitting hurts readability
        self, on_trade: Callable[[TradeRecord], None] | None = None
    ) -> BacktestReport:
        """Execute the backtest and return a :class:`BacktestReport`."""
        cfg = self.config
        grid = _decision_grid(cfg.start_date, cfg.end_date, cfg.frequency)
        if not grid:
            return _aggregate_report([], cfg.frequency, 0.0)

        cost_tracker = CostTracker(budget_cap_usd=cfg.budget_cap_usd)
        restore = self._maybe_install_stub_llm()
        try:
            graph = TradingAgentsGraph(config=cfg.trading_config, callbacks=[cost_tracker])
            trades: list[TradeRecord] = []
            stop = False

            for ticker in cfg.tickers:
                if stop:
                    break
                for decision_date in grid:
                    if stop:
                        break
                    try:
                        state, recommendation = graph.propagate(ticker, decision_date)
                    except CostBudgetExceeded as exc:
                        logger.warning("Backtest halted: %s", exc)
                        stop = True
                        break
                    except Exception as exc:
                        logger.exception("propagate failed for %s %s", ticker, decision_date)
                        trades.append(
                            TradeRecord(
                                ticker=ticker,
                                decision_date=decision_date,
                                recommendation=TradeRecommendation(signal="HOLD"),
                                notes=f"propagate error: {exc!s}",
                            )
                        )
                        continue

                    record = self._score_trade(ticker, decision_date, recommendation)
                    if cfg.reflect_after_each_trade and not cfg.dry_run:
                        try:
                            graph.reflect_and_remember(record.realised_return, state=state)
                        except Exception:
                            logger.warning(
                                "reflect_and_remember failed for %s %s",
                                ticker,
                                decision_date,
                                exc_info=True,
                            )
                    trades.append(record)
                    if on_trade is not None:
                        on_trade(record)
        finally:
            if restore is not None:
                restore()

        return _aggregate_report(trades, cfg.frequency, cost_tracker.total_cost_usd)

    def _score_trade(
        self, ticker: str, decision_date: str, recommendation: TradeRecommendation
    ) -> TradeRecord:
        """Compute entry / exit / realised return for one decision."""
        cfg = self.config
        decision_dt = datetime.strptime(decision_date, "%Y-%m-%d")
        # _resolve_history_with_cache builds a [curr_date - 15y, curr_date + 1d]
        # window. For backtest scoring we also need the next `horizon_days`
        # bars to mark each trade to market, so shift the reference forward
        # by horizon + a 7-day padding for weekends / holidays.
        score_ref_dt = decision_dt + timedelta(days=cfg.horizon_days + 7)
        try:
            _, history, _ = _resolve_history_with_cache(ticker, score_ref_dt)
        except Exception as exc:
            logger.warning("History fetch failed for %s %s: %s", ticker, decision_date, exc)
            return TradeRecord(
                ticker=ticker,
                decision_date=decision_date,
                recommendation=recommendation,
                notes=f"history error: {exc!s}",
            )

        _entry_date, entry_price = _entry_price_on(history, decision_date)
        exit_date, exit_price = _exit_price_after_horizon(history, decision_date, cfg.horizon_days)
        if entry_price is None or exit_price is None:
            return TradeRecord(
                ticker=ticker,
                decision_date=decision_date,
                recommendation=recommendation,
                entry_price=entry_price,
                exit_date=exit_date,
                exit_price=exit_price,
                notes="incomplete price data; realised_return defaulted to 0",
            )

        realised = _signed_return(
            recommendation.signal,
            entry_price,
            exit_price,
            recommendation.size_fraction,
            cfg.max_position_fraction,
        )
        return TradeRecord(
            ticker=ticker,
            decision_date=decision_date,
            recommendation=recommendation,
            entry_price=entry_price,
            exit_date=exit_date,
            exit_price=exit_price,
            realised_return=realised,
        )


__all__ = [
    "BacktestConfig",
    "BacktestReport",
    "Backtester",
    "CostBudgetExceeded",
    "CostTracker",
    "StubChatModel",
    "TradeRecord",
]
