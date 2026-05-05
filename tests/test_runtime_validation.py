import pytest

from tradingagents.graph.setup import GraphSetup
from tradingagents.interface.cli import _normalize_trade_date, _normalize_selected_analysts
from tradingagents.graph.trading_graph import _safe_path_component


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
