from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest
from langchain_core.messages import HumanMessage

from tradingagents import backtest as backtest_module
from tradingagents.graph import trading_graph as trading_graph_module
from tradingagents.config import TradingAgentsConfig
from tradingagents.backtest import (
    Backtester,
    CostTracker,
    TradeRecord,
    StubChatModel,
    BacktestConfig,
    CostBudgetExceeded,
    _decision_grid,
    _signed_return,
    _entry_price_on,
    _aggregate_report,
    _exit_price_after_horizon,
)
from tradingagents.graph.signal_processing import TradeRecommendation
from tradingagents.agents.utils.agent_states import AgentState


def _fake_history(start: str = "2024-01-01", n: int = 30) -> pd.DataFrame:
    """Build a deterministic upward OHLCV series for backtest scoring."""
    dates = pd.bdate_range(start=start, periods=n)
    closes = [100.0 + i for i in range(n)]
    return pd.DataFrame({
        "Date": dates,
        "Open": closes,
        "High": [c + 1 for c in closes],
        "Low": [c - 1 for c in closes],
        "Close": closes,
        "Volume": [1_000_000] * n,
    })


def _stub_trading_config() -> TradingAgentsConfig:
    return TradingAgentsConfig(
        llm_provider="google_genai",
        deep_think_llm="stub",
        quick_think_llm="stub",
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_recur_limit=30,
        reasoning_effort="low",
        response_language="en-US",
    )


def test_decision_grid_weekly_picks_fridays() -> None:
    grid = _decision_grid("2024-01-01", "2024-01-31", "weekly")

    assert grid
    assert all(pd.Timestamp(d).day_name() == "Friday" for d in grid)


def test_decision_grid_daily_uses_business_days() -> None:
    grid = _decision_grid("2024-01-01", "2024-01-05", "daily")

    # 5 weekdays in Jan 1-5 2024 (Mon-Fri).
    assert len(grid) == 5
    assert grid[0] == "2024-01-01"
    assert grid[-1] == "2024-01-05"


def test_entry_and_exit_prices_track_horizon() -> None:
    history = _fake_history(start="2024-01-01", n=10)

    entry_date, entry_price = _entry_price_on(history, "2024-01-03")
    exit_date, exit_price = _exit_price_after_horizon(history, "2024-01-03", horizon_days=3)

    # 2024-01-03 was a Wednesday so it is itself a trading day.
    assert entry_date == "2024-01-03"
    assert entry_price == 102.0
    # Three bars later: Thu Jan 4 -> Fri Jan 5 -> Mon Jan 8 (horizon hits Jan 8).
    assert exit_date == "2024-01-08"
    assert exit_price == 105.0


def test_signed_return_handles_each_signal() -> None:
    # Upward move
    assert _signed_return("BUY", 100.0, 110.0, 0.5, 0.2) == pytest.approx(0.02)  # capped at 0.2
    # SELL profits from a downward move
    assert _signed_return("SELL", 100.0, 90.0, 0.5, 0.5) == pytest.approx(0.05)
    # HOLD never moves the needle
    assert _signed_return("HOLD", 100.0, 200.0, 1.0, 1.0) == 0.0


def test_aggregate_report_computes_metrics() -> None:
    trades = [
        TradeRecord(
            ticker="AAA",
            decision_date="2024-01-05",
            recommendation=TradeRecommendation(signal="BUY"),
            entry_price=100.0,
            exit_date="2024-01-12",
            exit_price=105.0,
            realised_return=0.05,
        ),
        TradeRecord(
            ticker="AAA",
            decision_date="2024-01-12",
            recommendation=TradeRecommendation(signal="SELL"),
            entry_price=105.0,
            exit_date="2024-01-19",
            exit_price=110.0,
            realised_return=-0.05,
        ),
        TradeRecord(
            ticker="AAA",
            decision_date="2024-01-19",
            recommendation=TradeRecommendation(signal="HOLD"),
            entry_price=110.0,
            exit_date="2024-01-26",
            exit_price=112.0,
            realised_return=0.0,
        ),
    ]

    report = _aggregate_report(trades, "weekly", cost_usd=1.5)

    assert report.n_buy == 1
    assert report.n_sell == 1
    assert report.n_hold == 1
    assert report.estimated_cost_usd == 1.5
    assert report.hit_rate == pytest.approx(1 / 3)
    # Worst drawdown is negative or zero
    assert report.worst_drawdown <= 0.0


def test_cost_tracker_raises_when_budget_exceeded() -> None:
    tracker = CostTracker(budget_cap_usd=0.001)
    fake_response = MagicMock()
    fake_response.llm_output = {
        "model_name": "gemini-flash-latest",
        "token_usage": {"prompt_tokens": 100_000, "completion_tokens": 100_000},
    }

    with pytest.raises(CostBudgetExceeded):
        tracker.on_llm_end(fake_response)


def test_stub_chat_model_emits_canonical_signal_for_risk_judge() -> None:
    stub = StubChatModel()
    result = stub._generate([
        HumanMessage(
            content=("you are the risk management judge.\nProvide a structured recommendation...")
        )
    ])

    text = result.generations[0].message.content
    assert "FINAL TRANSACTION PROPOSAL" in text
    assert "```json" in text


def test_backtester_dry_run_completes_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end smoke: dry_run swaps in the stub LLM and the grid produces trades."""
    fake_history = _fake_history(start="2024-01-01", n=40)
    monkeypatch.setattr(
        backtest_module,
        "_resolve_history_with_cache",
        lambda symbol, dt: (symbol, fake_history.copy(), [symbol]),
    )

    # Avoid the real propagate() — it would build a full LangGraph. The
    # stub model the harness installs would short-circuit each node, but
    # the full graph still wires real tool nodes that the stub won't
    # exercise. For the dry-run smoke we patch propagate to a canned BUY.
    def fake_propagate(
        self: Any,  # noqa: ANN401  # self type only used by monkeypatch
        company_name: str,
        trade_date: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[AgentState, TradeRecommendation]:
        state = AgentState(
            company_of_interest=company_name,
            trade_date=trade_date,
            market_report="stub",
            sentiment_report="stub",
            news_report="stub",
            fundamentals_report="stub",
            situation_summary="stub",
        )
        recommendation = TradeRecommendation(
            signal="BUY", size_fraction=0.5, confidence=0.6, rationale="stub"
        )
        return state, recommendation

    monkeypatch.setattr(trading_graph_module.TradingAgentsGraph, "propagate", fake_propagate)

    config = BacktestConfig(
        tickers=["AAA"],
        start_date="2024-01-05",
        end_date="2024-02-29",
        frequency="weekly",
        horizon_days=3,
        dry_run=True,
        reflect_after_each_trade=False,
        trading_config=_stub_trading_config(),
    )

    report = Backtester(config=config).run()

    assert report.trades, "Expected at least one trade on a non-empty weekly grid"
    assert all(t.recommendation.signal == "BUY" for t in report.trades)
    # Upward synthetic price + capped size -> positive realised returns
    assert report.avg_trade_return > 0
    assert report.n_buy == len(report.trades)
    assert report.n_hold == 0


def test_backtester_uses_fresh_graph_per_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: TradingAgentsGraph state (self.ticker, log_states_dict)
    is mutable per-run; reusing one instance across tickers would cross-
    contaminate per-ticker log files (Copilot review on PR #49).
    """
    instantiations: list[str] = []

    real_init = trading_graph_module.TradingAgentsGraph.__init__

    def counting_init(self: Any, **kwargs: Any) -> None:  # noqa: ANN401
        real_init(self, **kwargs)
        # The constructor does not yet know the ticker; record by id so the
        # test asserts on the *number* of fresh instances rather than tickers.
        instantiations.append(f"graph#{len(instantiations)}")

    monkeypatch.setattr(trading_graph_module.TradingAgentsGraph, "__init__", counting_init)

    fake_history = _fake_history(start="2024-01-01", n=40)
    monkeypatch.setattr(
        backtest_module,
        "_resolve_history_with_cache",
        lambda symbol, dt: (symbol, fake_history.copy(), [symbol]),
    )

    def fake_propagate(
        self: Any,  # noqa: ANN401
        company_name: str,
        trade_date: str,
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[AgentState, TradeRecommendation]:
        state = AgentState(company_of_interest=company_name, trade_date=trade_date)
        rec = TradeRecommendation(signal="BUY")
        return state, rec

    monkeypatch.setattr(trading_graph_module.TradingAgentsGraph, "propagate", fake_propagate)

    config = BacktestConfig(
        tickers=["AAA", "BBB", "CCC"],
        start_date="2024-01-05",
        end_date="2024-01-31",
        frequency="weekly",
        horizon_days=3,
        dry_run=True,
        reflect_after_each_trade=False,
        trading_config=_stub_trading_config(),
    )

    Backtester(config=config).run()

    # One graph per ticker, regardless of how many decision dates each ticker has.
    assert len(instantiations) == 3, (
        f"Expected one TradingAgentsGraph instantiation per ticker, got {len(instantiations)}"
    )
