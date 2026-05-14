import pytest
from langchain_core.messages import AIMessage

from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.agents.utils.agent_states import AgentState, InvestDebateState, RiskDebateState


@pytest.mark.parametrize(
    ("method_name", "tools_node", "clear_node"),
    [
        ("should_continue_market", "tools_market", "Msg Clear Market"),
        ("should_continue_social", "tools_social", "Msg Clear Social"),
        ("should_continue_news", "tools_news", "Msg Clear News"),
        ("should_continue_fundamentals", "tools_fundamentals", "Msg Clear Fundamentals"),
    ],
)
def test_analyst_routing_uses_tool_calls_to_continue_or_clear(
    method_name: str, tools_node: str, clear_node: str
) -> None:
    logic = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=2)
    method = getattr(logic, method_name)

    with_tool = AgentState(
        messages=[
            AIMessage(
                content="",
                tool_calls=[{"name": "get_stock_data", "args": {"ticker": "AAPL"}, "id": "1"}],
            )
        ]
    )
    without_tool = AgentState(messages=[AIMessage(content="complete")])

    assert method(with_tool) == tools_node
    assert method(without_tool) == clear_node


def test_investment_debate_routes_to_research_manager_at_cutoff() -> None:
    logic = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=1)
    state = AgentState(investment_debate_state=InvestDebateState(count=4))

    assert logic.should_continue_debate(state) == "Research Manager"


@pytest.mark.parametrize(
    ("current_response", "expected"),
    [
        ("Bull Researcher: upside case", "Bear Researcher"),
        ("Bear Researcher: downside case", "Bull Researcher"),
        ("", "Bull Researcher"),
    ],
)
def test_investment_debate_alternates_speakers_before_cutoff(
    current_response: str, expected: str
) -> None:
    logic = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=1)
    state = AgentState(
        investment_debate_state=InvestDebateState(count=1, current_response=current_response)
    )

    assert logic.should_continue_debate(state) == expected


def test_risk_debate_routes_to_judge_at_cutoff() -> None:
    logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    state = AgentState(risk_debate_state=RiskDebateState(count=3))

    assert logic.should_continue_risk_analysis(state) == "Risk Judge"


@pytest.mark.parametrize(
    ("latest_speaker", "expected"),
    [
        ("Aggressive Analyst", "Conservative Analyst"),
        ("Conservative Analyst", "Neutral Analyst"),
        ("Neutral Analyst", "Aggressive Analyst"),
        ("", "Aggressive Analyst"),
    ],
)
def test_risk_debate_cycles_speakers_before_cutoff(latest_speaker: str, expected: str) -> None:
    logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=2)
    state = AgentState(risk_debate_state=RiskDebateState(count=1, latest_speaker=latest_speaker))

    assert logic.should_continue_risk_analysis(state) == expected
