import pytest

from tradingagents.runtime import RunContext, set_run_context, reset_run_context
from tradingagents.graph.setup import GraphSetup
from tradingagents.interface.cli import _normalize_trade_date, _normalize_selected_analysts
from tradingagents.graph.trading_graph import _safe_path_component
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fundamental_data_tools import get_fundamentals


def test_normalize_trade_date_rejects_bad_format() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _normalize_trade_date("2024/01/01")


def test_normalize_selected_analysts_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown analyst"):
        _normalize_selected_analysts(["market", "macro"])


def test_graph_setup_deduplicates_selected_analysts() -> None:
    assert GraphSetup.validate_selected_analysts(["market", "Market", "news"]) == [
        "market",
        "news",
    ]


def test_safe_path_component_blocks_path_traversal() -> None:
    assert _safe_path_component("../AAPL/../../x") == "AAPL_.._.._x"


def test_tool_guard_rejects_future_end_date_under_run_context() -> None:
    token = set_run_context(
        RunContext(ticker="AAPL", trade_date="2024-01-05", response_language="en-US")
    )
    try:
        result = get_stock_data.invoke({
            "symbol": "AAPL",
            "start_date": "2024-01-01",
            "end_date": "2024-01-06",
        })
    finally:
        reset_run_context(token)

    assert result.startswith("[TOOL_ERROR]")
    assert "end_date=2024-01-06" in result
    assert "trade_date is 2024-01-05" in result


def test_tool_guard_rejects_future_curr_date_under_run_context() -> None:
    token = set_run_context(
        RunContext(ticker="AAPL", trade_date="2024-01-05", response_language="en-US")
    )
    try:
        result = get_fundamentals.invoke({"ticker": "AAPL", "curr_date": "2024-01-06"})
    finally:
        reset_run_context(token)

    assert result.startswith("[TOOL_ERROR]")
    assert "curr_date=2024-01-06" in result
