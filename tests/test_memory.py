import json
from pathlib import Path

import pytest

from tradingagents.agents.utils.memory import FinancialSituationMemory


def test_memory_persists_loads_and_clears_jsonl(tmp_path: Path) -> None:
    storage_path = tmp_path / "memories" / "trader.jsonl"
    memory = FinancialSituationMemory(name="trader", storage_path=storage_path)

    memory.add_situations([
        ("AAPL earnings beat with strong services growth", "Favor BUY on pullbacks."),
        ("Treasury yields spike and duration sells off", "Reduce long exposure."),
    ])

    assert storage_path.exists()
    rows = [json.loads(line) for line in storage_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "situation": "AAPL earnings beat with strong services growth",
            "recommendation": "Favor BUY on pullbacks.",
        },
        {
            "situation": "Treasury yields spike and duration sells off",
            "recommendation": "Reduce long exposure.",
        },
    ]

    reloaded = FinancialSituationMemory(name="trader", storage_path=storage_path)
    assert reloaded.documents == memory.documents
    assert reloaded.recommendations == memory.recommendations
    assert reloaded.bm25 is not None

    reloaded.clear()
    assert reloaded.documents == []
    assert reloaded.recommendations == []
    assert reloaded.bm25 is None
    assert not storage_path.exists()


def test_memory_load_skips_malformed_jsonl_lines(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    storage_path = tmp_path / "bear.jsonl"
    storage_path.write_text(
        "\n".join([
            '{"situation": "valid macro stress", "recommendation": "Prefer HOLD."}',
            "{not json",
            "",
        ]),
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        memory = FinancialSituationMemory(name="bear", storage_path=storage_path)

    assert memory.documents == ["valid macro stress"]
    assert memory.recommendations == ["Prefer HOLD."]
    assert "Skipping malformed memory line" in caplog.text


def test_memory_get_memories_returns_ranked_bm25_matches() -> None:
    memory = FinancialSituationMemory(name="bull")
    memory.add_situations([
        ("iphone services earnings beat margin expansion", "Bull lesson"),
        ("crude oil inventory supply shock", "Energy lesson"),
        ("treasury duration yields curve inversion", "Rates lesson"),
    ])

    matches = memory.get_memories("services earnings iphone momentum", n_matches=2)

    assert len(matches) == 2
    assert matches[0]["matched_situation"] == "iphone services earnings beat margin expansion"
    assert matches[0]["recommendation"] == "Bull lesson"
    assert matches[0]["similarity_score"] == pytest.approx(1.0)


def test_memory_get_memories_returns_empty_when_uninitialized() -> None:
    memory = FinancialSituationMemory(name="empty")

    assert memory.get_memories("anything", n_matches=3) == []
