import pytest

from tradingagents.graph.signal_processing import SignalProcessor, extract_trade_signal


def test_extract_trade_signal_prefers_final_marker() -> None:
    text = "The body mentions HOLD as a risk case.\nFINAL TRANSACTION PROPOSAL: **BUY**"

    assert extract_trade_signal(text) == "BUY"


def test_extract_trade_signal_handles_list_content() -> None:
    content = [{"type": "text", "text": "FINAL TRANSACTION PROPOSAL: **SELL**"}]

    assert extract_trade_signal(content) == "SELL"


def test_extract_trade_signal_falls_back_to_hold_on_ambiguous(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ambiguous / multi-signal output now defaults to HOLD with a warning,
    instead of raising and aborting an in-flight 12-agent paid run.
    """
    with caplog.at_level("WARNING"):
        result = extract_trade_signal("BUY looks attractive, but HOLD is also defensible.")
    assert result == "HOLD"
    assert "ambiguous" in caplog.text.lower()


def test_extract_trade_signal_falls_back_to_hold_on_missing_decision(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Empty / no-decision output also defaults to HOLD with a warning."""
    with caplog.at_level("WARNING"):
        result = extract_trade_signal("No canonical trade decision was written.")
    assert result == "HOLD"
    assert "no buy/sell/hold" in caplog.text.lower()


def test_signal_processor_does_not_require_llm() -> None:
    processor = SignalProcessor()

    assert processor.process_signal("FINAL TRANSACTION PROPOSAL: **HOLD**") == "HOLD"
