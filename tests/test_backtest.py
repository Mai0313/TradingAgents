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
    _split_for_index,
    _aggregate_report,
    _exit_price_after_horizon,
)
from tradingagents.interface.backtest import _parse_split_fractions
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


def test_signed_return_applies_costs_and_shorting_availability() -> None:
    assert _signed_return(
        "BUY", 100.0, 110.0, 0.5, 0.5, transaction_cost_bps=10, slippage_bps=5
    ) == pytest.approx(0.0485)
    assert _signed_return("SELL", 100.0, 90.0, 0.5, 0.5, allow_short=False) == 0.0


def test_split_for_index_uses_chronological_fractions() -> None:
    fractions = (0.5, 0.25, 0.25)

    assert [_split_for_index(i, 8, fractions) for i in range(8)] == [
        "train",
        "train",
        "train",
        "train",
        "validation",
        "validation",
        "test",
        "test",
    ]


def test_parse_split_fractions_accepts_fire_list_values() -> None:
    assert _parse_split_fractions([0.6, "0.2", 0.2]) == (0.6, 0.2, 0.2)
    assert _parse_split_fractions(("0.7", "0.2", "0.1")) == (0.7, 0.2, 0.1)


def test_aggregate_report_computes_metrics() -> None:
    trades = [
        TradeRecord(
            ticker="AAA",
            decision_date="2024-01-05",
            dataset_split="train",
            recommendation=TradeRecommendation(signal="BUY"),
            entry_price=100.0,
            exit_date="2024-01-12",
            exit_price=105.0,
            realised_return=0.05,
            benchmark_returns={"buy_and_hold": 0.05, "always_hold": 0.0},
        ),
        TradeRecord(
            ticker="AAA",
            decision_date="2024-01-12",
            dataset_split="validation",
            recommendation=TradeRecommendation(signal="SELL"),
            entry_price=105.0,
            exit_date="2024-01-19",
            exit_price=110.0,
            realised_return=-0.05,
            benchmark_returns={"buy_and_hold": 0.04, "always_hold": 0.0},
        ),
        TradeRecord(
            ticker="AAA",
            decision_date="2024-01-19",
            dataset_split="test",
            recommendation=TradeRecommendation(signal="HOLD", size_fraction=0.0),
            entry_price=110.0,
            exit_date="2024-01-26",
            exit_price=112.0,
            realised_return=0.0,
            benchmark_returns={"buy_and_hold": 0.01, "always_hold": 0.0},
        ),
    ]

    report = _aggregate_report(trades, "weekly", cost_usd=1.5)

    assert report.n_buy == 1
    assert report.n_sell == 1
    assert report.n_hold == 1
    assert report.estimated_cost_usd == 1.5
    assert report.hit_rate == pytest.approx(1 / 3)
    assert report.benchmarks["buy_and_hold"].total_return > 0
    assert report.benchmarks["always_hold"].total_return == 0
    assert set(report.split_reports) == {"train", "validation", "test"}
    assert report.signal_distribution == {"BUY": 1, "SELL": 1, "HOLD": 1}
    assert report.warning_rate == 0.0
    assert report.prompt_versions["backtest_evaluation"] == "backtest-eval-v1"
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
    assert {trade.dataset_split for trade in report.trades} <= {"train", "validation", "test"}
    assert report.model_names["llm_provider"] == "google_genai"
    assert report.signal_distribution["BUY"] == len(report.trades)
    assert set(report.benchmarks) == {
        "always_hold",
        "buy_and_hold",
        "random_baseline",
        "sma_crossover",
    }


def test_backtester_reflects_only_after_all_tickers_for_same_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Walk-forward memory must not leak same-date or future ticker outcomes."""
    events: list[tuple[str, str, str]] = []
    fake_history = _fake_history(start="2024-01-01", n=30)
    monkeypatch.setattr(
        backtest_module,
        "_resolve_history_with_cache",
        lambda symbol, dt: (symbol, fake_history.copy(), [symbol]),
    )

    class FakeGraph:
        def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
            _ = kwargs

        def propagate(
            self, company_name: str, trade_date: str
        ) -> tuple[AgentState, TradeRecommendation]:
            events.append(("propagate", trade_date, company_name))
            return (
                AgentState(company_of_interest=company_name, trade_date=trade_date),
                TradeRecommendation(signal="BUY", size_fraction=0.1),
            )

        def reflect_and_remember(
            self, returns_losses: float, *, state: AgentState, outcome_context: object
        ) -> dict[str, object]:
            _ = (returns_losses, outcome_context)
            events.append(("reflect", state.trade_date, state.company_of_interest))
            return {}

    monkeypatch.setattr(backtest_module, "TradingAgentsGraph", FakeGraph)

    config = BacktestConfig(
        tickers=["AAA", "BBB"],
        start_date="2024-01-05",
        end_date="2024-01-12",
        frequency="weekly",
        horizon_days=3,
        reflect_after_each_trade=True,
        walk_forward=True,
        trading_config=_stub_trading_config(),
    )

    Backtester(config=config).run()

    assert events == [
        ("propagate", "2024-01-05", "AAA"),
        ("propagate", "2024-01-05", "BBB"),
        ("reflect", "2024-01-05", "AAA"),
        ("reflect", "2024-01-05", "BBB"),
        ("propagate", "2024-01-12", "AAA"),
        ("propagate", "2024-01-12", "BBB"),
        ("reflect", "2024-01-12", "AAA"),
        ("reflect", "2024-01-12", "BBB"),
    ]


def test_backtester_uses_fresh_graph_per_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each decision needs a fresh graph so persisted memory is reloaded chronologically."""
    instantiations: list[str] = []

    fake_history = _fake_history(start="2024-01-01", n=40)
    monkeypatch.setattr(
        backtest_module,
        "_resolve_history_with_cache",
        lambda symbol, dt: (symbol, fake_history.copy(), [symbol]),
    )

    class FakeGraph:
        def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
            _ = kwargs
            instantiations.append(f"graph#{len(instantiations)}")

        def propagate(
            self, company_name: str, trade_date: str
        ) -> tuple[AgentState, TradeRecommendation]:
            state = AgentState(company_of_interest=company_name, trade_date=trade_date)
            rec = TradeRecommendation(signal="BUY")
            return state, rec

    monkeypatch.setattr(backtest_module, "TradingAgentsGraph", FakeGraph)

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

    expected = len(config.tickers) * len(
        _decision_grid(config.start_date, config.end_date, "weekly")
    )
    assert len(instantiations) == expected


def test_backtester_propagate_error_hold_does_not_count_as_parser_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingGraph:
        def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
            _ = kwargs

        def propagate(
            self, company_name: str, trade_date: str
        ) -> tuple[AgentState, TradeRecommendation]:
            _ = (company_name, trade_date)
            raise RuntimeError("boom")

    monkeypatch.setattr(backtest_module, "TradingAgentsGraph", FailingGraph)

    config = BacktestConfig(
        tickers=["AAA"],
        start_date="2024-01-05",
        end_date="2024-01-05",
        frequency="weekly",
        dry_run=True,
        reflect_after_each_trade=False,
        trading_config=_stub_trading_config(),
    )

    report = Backtester(config=config).run()

    assert report.trades[0].recommendation.signal == "HOLD"
    assert report.trades[0].recommendation.size_fraction == 0.0
    assert report.trades[0].recommendation.warning_message is None
    assert report.warning_rate == 0.0
    assert "propagate error: boom" in report.trades[0].notes
