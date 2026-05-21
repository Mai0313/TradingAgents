from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tradingagents.graph import reflection as reflection_module
from tradingagents.graph.reflection import (
    Reflector,
    ReflectionOutcomeContext,
    _flatten_content,
    parse_reflection_scores,
)
from tradingagents.graph.signal_processing import TradeRecommendation
from tradingagents.agents.utils.agent_states import AgentState, RiskDebateState, InvestDebateState


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("plain", "plain"),
        ([{"type": "text", "text": "alpha"}, {"content": " beta"}, " gamma"], "alpha beta gamma"),
        (123, "123"),
    ],
)
def test_flatten_content_normalizes_provider_response_shapes(
    content: object, expected: str
) -> None:
    assert _flatten_content(content) == expected


def test_reflect_on_component_formats_prompt_and_flattens_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = SimpleNamespace(
        content=[{"type": "text", "text": "lesson "}, {"type": "text", "text": "learned"}]
    )
    monkeypatch.setattr(reflection_module, "load_prompt", lambda name: f"prompt:{name}")

    reflector = Reflector(quick_thinking_llm=fake_llm)
    result = reflector._reflect_on_component("decision report", "market situation", 0.12)

    assert result == "lesson learned"
    messages = fake_llm.invoke.call_args.args[0]
    assert messages[0].content == "prompt:reflector"
    assert "Returns: 0.12" in messages[1].content
    assert "# Structured outcome" not in messages[1].content
    assert "Analysis/Decision: decision report" in messages[1].content
    assert "Objective Market Reports for Reference: market situation" in messages[1].content


def test_parse_reflection_scores_returns_structured_rubric() -> None:
    scores = parse_reflection_scores(
        """Lesson prose.

### Reflection scores
- macro: 4
- technicals: 3
- price_action: 4
- news_flow: 2
- sentiment: 3
- fundamentals: 5
- overall_reasoning: 4
- outcome_quality: 2
- lesson_category: bad_luck
"""
    )

    assert scores is not None
    assert scores.macro == 4
    assert scores.lesson_category == "bad_luck"


def test_reflector_stores_situation_summary_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = SimpleNamespace(content="stored lesson")
    fake_memory = MagicMock()
    monkeypatch.setattr(reflection_module, "load_prompt", lambda name: f"prompt:{name}")

    state = AgentState(
        market_report="market",
        sentiment_report="sentiment",
        news_report="news",
        fundamentals_report="fundamentals",
        situation_summary="compact summary",
        trader_investment_plan="trader plan",
        company_of_interest="AAPL",
        trade_date="2024-01-05",
        final_trade_recommendation=TradeRecommendation(signal="BUY"),
    )

    scores = Reflector(quick_thinking_llm=fake_llm).reflect_trader(
        state,
        0.05,
        fake_memory,
        ReflectionOutcomeContext(
            entry_price=100.0,
            exit_price=105.0,
            exit_date="2024-01-12",
            horizon_days=5,
            benchmark_returns={"buy_and_hold": 0.03},
        ),
    )

    stored = fake_memory.add_situations.call_args.args[0][0]
    assert stored[0] == "compact summary"
    assert stored[1] == "stored lesson"
    assert stored[2]["ticker"] == "AAPL"
    assert stored[2]["trade_date"] == "2024-01-05"
    assert stored[2]["signal"] == "BUY"
    assert stored[2]["component"] == "trader"
    assert scores is None
    prompt = fake_llm.invoke.call_args.args[0][1].content
    assert "- entry_price: 100.0" in prompt
    assert "- exit_price: 105.0" in prompt
    assert "- benchmark_returns: {'buy_and_hold': 0.03}" in prompt


def test_reflector_falls_back_to_combined_reports_when_summary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = SimpleNamespace(content="risk lesson")
    fake_memory = MagicMock()
    monkeypatch.setattr(reflection_module, "load_prompt", lambda name: f"prompt:{name}")

    state = AgentState(
        market_report="market",
        sentiment_report="sentiment",
        news_report="news",
        fundamentals_report="fundamentals",
        risk_debate_state=RiskDebateState(judge_decision="risk verdict"),
        investment_debate_state=InvestDebateState(judge_decision="invest verdict"),
    )

    Reflector(quick_thinking_llm=fake_llm).reflect_risk_manager(state, -0.03, fake_memory)

    stored = fake_memory.add_situations.call_args.args[0][0]
    assert stored[0] == state.combined_reports
    assert stored[1] == "risk lesson"
    assert stored[2]["component"] == "risk_manager"
