import re
from typing import Any
from pathlib import Path
from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.tool_registry import ANALYST_TOOL_REGISTRY
from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst

_PROMPT_DIR = Path(__file__).resolve().parents[1] / "src/tradingagents/agents/prompts"
_TOOL_CALL_PATTERN = re.compile(r"`(get_[a-z_]+)\(")


class CapturingLLM:
    """Minimal LLM fake that records bound tool names and returns one AI message."""

    def __init__(self) -> None:
        self.bound_tool_names: list[str] = []

    def bind_tools(self, tools: list[Any]) -> RunnableLambda:
        self.bound_tool_names = [tool.name for tool in tools]
        return RunnableLambda(lambda _input: AIMessage(content="stub report"))


def _tool_names(analyst_type: str) -> list[str]:
    return [tool.name for tool in ANALYST_TOOL_REGISTRY[analyst_type]]


def _state() -> AgentState:
    return AgentState(
        messages=[HumanMessage(content="AAPL")],
        company_of_interest="AAPL",
        trade_date="2024-05-10",
    )


def test_trading_graph_tool_nodes_match_registry(tmp_path: Path) -> None:
    config = TradingAgentsConfig(
        results_dir=tmp_path,
        llm_provider="google_genai",
        deep_think_llm="stub",
        quick_think_llm="stub",
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_recur_limit=30,
    )
    graph = TradingAgentsGraph(config=config)

    assert set(graph.tool_nodes) == set(ANALYST_TOOL_REGISTRY)
    for analyst_type, tools in ANALYST_TOOL_REGISTRY.items():
        assert list(graph.tool_nodes[analyst_type].tools_by_name) == [tool.name for tool in tools]


@pytest.mark.parametrize(
    ("analyst_type", "creator"),
    [
        ("market", create_market_analyst),
        ("social", create_social_media_analyst),
        ("news", create_news_analyst),
        ("fundamentals", create_fundamentals_analyst),
    ],
)
def test_analyst_nodes_bind_registered_tools(
    analyst_type: str, creator: Callable[[Any], Callable[[AgentState], dict[str, Any]]]
) -> None:
    llm = CapturingLLM()
    node = creator(llm)

    result = node(_state())

    assert result
    assert llm.bound_tool_names == _tool_names(analyst_type)


@pytest.mark.parametrize(
    ("analyst_type", "prompt_name"),
    [
        ("market", "market_analyst.md"),
        ("social", "news_sentiment_analyst.md"),
        ("news", "news_analyst.md"),
        ("fundamentals", "fundamentals_analyst.md"),
    ],
)
def test_prompt_tool_mentions_match_registry(analyst_type: str, prompt_name: str) -> None:
    text = (_PROMPT_DIR / prompt_name).read_text(encoding="utf-8")
    mentioned = sorted(set(_TOOL_CALL_PATTERN.findall(text)))

    assert mentioned == sorted(_tool_names(analyst_type))
