import pytest

from tradingagents.graph.signal_processing import extract_trade_signal


def test_extract_trade_signal_prefers_final_marker() -> None:
    text = "The body mentions HOLD as a risk case.\nFINAL TRANSACTION PROPOSAL: **BUY**"

    assert extract_trade_signal(text) == "BUY"


def test_extract_trade_signal_handles_list_content() -> None:
    content = [{"type": "text", "text": "FINAL TRANSACTION PROPOSAL: **SELL**"}]

    assert extract_trade_signal(content) == "SELL"


def test_extract_trade_signal_rejects_ambiguous_unmarked_text() -> None:
    with pytest.raises(ValueError, match="Ambiguous"):
        extract_trade_signal("BUY looks attractive, but HOLD is also defensible.")


def test_extract_trade_signal_rejects_missing_decision() -> None:
    with pytest.raises(ValueError, match="No BUY/SELL/HOLD"):
        extract_trade_signal("No canonical trade decision was written.")
