from pathlib import Path
from collections.abc import Iterator

from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

from tradingagents.config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.agents.utils.agent_states import AgentState


class FakeGraph:
    def __init__(self, chunks: list[AgentState]) -> None:
        self.chunks = chunks

    def stream(self, _init_state: AgentState, **_kwargs: object) -> Iterator[AgentState]:
        yield from self.chunks


def _config(tmp_path: Path) -> TradingAgentsConfig:
    return TradingAgentsConfig(
        results_dir=tmp_path,
        llm_provider="google_genai",
        deep_think_llm="stub",
        quick_think_llm="stub",
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_recur_limit=30,
    )


def _final_trade_decision() -> str:
    return """```json
{"signal": "BUY", "size_fraction": 0.25, "confidence": 0.8, "rationale": "stub"}
```
FINAL TRANSACTION PROPOSAL: **BUY**"""


def _graph_with_messages(tmp_path: Path) -> TradingAgentsGraph:
    human = HumanMessage(content="AAPL", id="h1")
    ai = AIMessage(content="Need market data.", id="a1")
    tool = ToolMessage(
        content='{"close": 195.12}', name="get_stock_data", tool_call_id="call-1", id="t1"
    )
    ta = TradingAgentsGraph(debug=False, config=_config(tmp_path))
    ta.__dict__["graph"] = FakeGraph([
        AgentState(messages=[human], company_of_interest="AAPL", trade_date="2024-05-10"),
        AgentState(messages=[human, ai], company_of_interest="AAPL", trade_date="2024-05-10"),
        AgentState(
            messages=[human, ai, tool],
            company_of_interest="AAPL",
            trade_date="2024-05-10",
            final_trade_decision=_final_trade_decision(),
        ),
    ])
    return ta


def test_propagate_returns_two_tuple_by_default(tmp_path: Path) -> None:
    result = _graph_with_messages(tmp_path).propagate(company_name="AAPL", trade_date="2024-05-10")

    assert len(result) == 2


def test_propagate_can_return_collected_messages(tmp_path: Path) -> None:
    state, recommendation, messages = _graph_with_messages(tmp_path).propagate(
        company_name="AAPL", trade_date="2024-05-10", return_messages=True
    )

    assert recommendation.signal == "BUY"
    assert state.final_trade_recommendation == recommendation
    assert [type(message) for message in messages] == [HumanMessage, AIMessage, ToolMessage]
    assert [message.content for message in messages] == [
        "AAPL",
        "Need market data.",
        '{"close": 195.12}',
    ]
