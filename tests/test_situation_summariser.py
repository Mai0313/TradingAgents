from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from tradingagents import llm as llm_module
from tradingagents.graph import trading_graph
from tradingagents.config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.preprocessors.situation_summariser import create_situation_summariser


def _make_state() -> AgentState:
    return AgentState(
        company_of_interest="AAPL",
        trade_date="2024-05-10",
        market_report="MACD bullish; 50 SMA rising.",
        sentiment_report="Headlines mostly positive on AI guidance.",
        news_report="Q1 earnings beat; iPhone unit growth surprised.",
        fundamentals_report="PE 28x; FCF margin 22%.",
    )


def test_situation_summariser_writes_to_situation_summary_field() -> None:
    fake_response = SimpleNamespace(content="### Ticker profile\n- AAPL big tech, USD.\n")
    llm = MagicMock()
    llm.invoke.return_value = fake_response

    node = create_situation_summariser(llm)
    result = node(_make_state())

    assert "situation_summary" in result
    assert "AAPL" in result["situation_summary"]
    # The node must invoke the LLM exactly once with a fully-formatted prompt.
    assert llm.invoke.call_count == 1
    prompt_arg = llm.invoke.call_args.args[0]
    assert "AAPL" in prompt_arg
    assert "2024-05-10" in prompt_arg
    assert "MACD bullish" in prompt_arg


def test_situation_summariser_flattens_list_content() -> None:
    # Some providers (Anthropic, Gemini 3) return list-shaped content.
    fake_response = SimpleNamespace(
        content=[{"type": "text", "text": "chunk-1 "}, {"type": "text", "text": "chunk-2"}]
    )
    llm = MagicMock()
    llm.invoke.return_value = fake_response

    node = create_situation_summariser(llm)
    result = node(_make_state())

    assert result["situation_summary"] == "chunk-1 \nchunk-2"


def test_graph_topology_contains_situation_summariser_between_analysts_and_bull(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Situation Summariser must sit between the last Msg Clear and the Bull Researcher.

    A stale topology that skips the summariser would silently regress the BM25
    retrieval quality without breaking any single-node test.
    """
    # Inject a fake build_chat_model so the test does not need API keys.
    monkeypatch.setattr(llm_module, "build_chat_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(trading_graph, "build_chat_model", lambda *a, **kw: MagicMock())

    config = TradingAgentsConfig(
        llm_provider="google_genai",
        deep_think_llm="x",
        quick_think_llm="x",
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_recur_limit=30,
        reasoning_effort="low",
        response_language="en-US",
    )
    ta = TradingAgentsGraph(config=config)

    compiled = ta.graph
    nodes: dict[str, Any] = compiled.get_graph().nodes
    assert "Situation Summariser" in nodes, sorted(nodes.keys())
    assert "Bull Researcher" in nodes

    # The summariser must have an incoming edge from a Msg Clear node and an
    # outgoing edge into Bull Researcher.
    edges = list(compiled.get_graph().edges)
    edge_pairs = [(e.source, e.target) for e in edges]
    assert ("Situation Summariser", "Bull Researcher") in edge_pairs
    assert any(
        src.startswith("Msg Clear") and tgt == "Situation Summariser" for src, tgt in edge_pairs
    ), edge_pairs
