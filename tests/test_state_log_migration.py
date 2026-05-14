import json
from pathlib import Path

import pytest

from tradingagents.interface.reflect import (
    _resolve_state_log,
    _migrate_state_log_v1_to_v2,
    _normalise_state_log_payload,
)


def _write_log(tmp_path: Path, ticker: str, date: str, payload: dict) -> Path:
    """Write a state log under ``<tmp_path>/<ticker>/full_states_log_*.json``."""
    ticker_dir = tmp_path / ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)
    path = ticker_dir / f"full_states_log_{ticker}_{date}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_migrate_v1_to_v2_wraps_as_runs() -> None:
    v1 = {"2024-05-10": {"company_of_interest": "AAPL"}}

    migrated = _migrate_state_log_v1_to_v2(v1)

    assert migrated == {"schema_version": 2, "runs": v1}


def test_normalise_treats_missing_schema_as_v1(tmp_path: Path) -> None:
    v1 = {"2024-05-10": {"company_of_interest": "AAPL"}}

    normalised = _normalise_state_log_payload(v1, log_path=tmp_path / "fake.json")

    assert normalised["schema_version"] == 2
    assert normalised["runs"] == v1


def test_normalise_keeps_known_schema(tmp_path: Path) -> None:
    v2 = {"schema_version": 2, "runs": {"2024-05-10": {"company_of_interest": "AAPL"}}}

    normalised = _normalise_state_log_payload(v2, log_path=tmp_path / "fake.json")

    assert normalised is v2  # no copy / mutation on the happy path


def test_normalise_warns_for_future_schema(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    future = {"schema_version": 99, "runs": {"2024-05-10": {"company_of_interest": "AAPL"}}}

    with caplog.at_level("WARNING"):
        normalised = _normalise_state_log_payload(future, log_path=tmp_path / "fake.json")

    assert normalised is future
    assert "newer than this code understands" in caplog.text


def test_resolve_state_log_reads_v1_log(tmp_path: Path) -> None:
    """End-to-end: a real v1 file on disk must be readable by the reflect path."""
    v1_payload = {
        "2024-05-10": {
            "company_of_interest": "AAPL",
            "trade_date": "2024-05-10",
            "market_report": "trend up",
            "investment_debate_state": {
                "bull_history": "",
                "bear_history": "",
                "history": "",
                "current_response": "",
                "judge_decision": "",
                "count": 0,
            },
            "risk_debate_state": {
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "history": "",
                "judge_decision": "",
                "count": 0,
            },
        }
    }
    _write_log(tmp_path, "AAPL", "2024-05-10", v1_payload)

    _path, raw = _resolve_state_log(tmp_path, "AAPL", "2024-05-10")

    assert raw["company_of_interest"] == "AAPL"
    assert raw["market_report"] == "trend up"


def test_resolve_state_log_reads_v2_log(tmp_path: Path) -> None:
    """v2 logs (current code's output shape) must continue to load."""
    v2_payload = {
        "schema_version": 2,
        "runs": {
            "2024-05-10": {
                "company_of_interest": "AAPL",
                "trade_date": "2024-05-10",
                "market_report": "trend up",
                "situation_summary": "compact snapshot",
                "investment_debate_state": {},
                "risk_debate_state": {},
            }
        },
    }
    _write_log(tmp_path, "AAPL", "2024-05-10", v2_payload)

    _path, raw = _resolve_state_log(tmp_path, "AAPL", "2024-05-10")

    assert raw["company_of_interest"] == "AAPL"
    assert raw["situation_summary"] == "compact snapshot"
