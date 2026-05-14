import pytest

from tradingagents.graph.signal_processing import (
    SignalProcessor,
    TradeRecommendation,
    extract_trade_signal,
    extract_trade_recommendation,
)


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


def test_signal_processor_returns_recommendation_with_signal() -> None:
    processor = SignalProcessor()
    rec = processor.process_signal("FINAL TRANSACTION PROPOSAL: **HOLD**")
    assert isinstance(rec, TradeRecommendation)
    assert rec.signal == "HOLD"


def test_extract_trade_recommendation_parses_full_json_block() -> None:
    text = """Reasoning prose here...

```json
{
  "signal": "BUY",
  "size_fraction": 0.6,
  "target_price": 175.0,
  "stop_loss": 155.0,
  "time_horizon_days": 10,
  "confidence": 0.72,
  "rationale": "Strong momentum and earnings beat."
}
```

FINAL TRANSACTION PROPOSAL: **BUY**
"""
    rec = extract_trade_recommendation(text)
    assert rec.signal == "BUY"
    assert rec.size_fraction == 0.6
    assert rec.target_price == 175.0
    assert rec.stop_loss == 155.0
    assert rec.time_horizon_days == 10
    assert rec.confidence == 0.72
    assert "momentum" in rec.rationale
    assert rec.warning_message is None


def test_extract_trade_recommendation_warns_on_signal_disagreement(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the JSON ``signal`` disagrees with the canonical line, canonical wins
    and the recommendation carries a warning_message documenting the mismatch.
    """
    text = """Reasoning...

```json
{
  "signal": "BUY",
  "size_fraction": 0.3,
  "target_price": null,
  "stop_loss": null,
  "time_horizon_days": null,
  "confidence": 0.4,
  "rationale": "Net positive but with caveats."
}
```

FINAL TRANSACTION PROPOSAL: **SELL**
"""
    rec = extract_trade_recommendation(text)
    assert rec.signal == "SELL", "canonical line must win"
    assert rec.warning_message is not None
    assert "BUY" in rec.warning_message
    assert "SELL" in rec.warning_message


def test_extract_trade_recommendation_falls_back_when_json_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    text = "No JSON anywhere.\nFINAL TRANSACTION PROPOSAL: **HOLD**\n"
    rec = extract_trade_recommendation(text)
    assert rec.signal == "HOLD"
    assert rec.size_fraction == 0.5
    assert rec.confidence == 0.5
    assert rec.warning_message is not None
    assert "no parseable json" in rec.warning_message.lower()


def test_extract_trade_recommendation_falls_back_when_json_malformed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    text = """Reasoning...

```json
{ "signal": "BUY", "size_fraction": 0.6,    <-- trailing garbage breaks parse
```

FINAL TRANSACTION PROPOSAL: **BUY**
"""
    with caplog.at_level("WARNING"):
        rec = extract_trade_recommendation(text)
    assert rec.signal == "BUY"
    assert rec.size_fraction == 0.5
    assert rec.warning_message is not None
    assert "no parseable json" in rec.warning_message.lower()


def test_extract_trade_recommendation_handles_empty_input() -> None:
    rec = extract_trade_recommendation(None)
    assert rec.signal == "HOLD"
    assert rec.warning_message is not None
