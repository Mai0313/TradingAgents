# TradingAgents/graph/conditional_logic.py

from typing import Literal

from pydantic import Field, BaseModel

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic(BaseModel):
    max_debate_rounds: int = Field(
        default=1,
        title="Max Debate Rounds",
        description="Maximum number of Bull/Bear investment debate rounds",
    )
    max_risk_discuss_rounds: int = Field(
        default=1,
        title="Max Risk Discussion Rounds",
        description="Maximum number of Risk debate rounds",
    )

    def should_continue_market(
        self, state: AgentState
    ) -> Literal["tools_market", "Msg Clear Market"]:
        return "tools_market" if state.messages[-1].tool_calls else "Msg Clear Market"

    def should_continue_social(
        self, state: AgentState
    ) -> Literal["tools_social", "Msg Clear Social"]:
        return "tools_social" if state.messages[-1].tool_calls else "Msg Clear Social"

    def should_continue_news(self, state: AgentState) -> Literal["tools_news", "Msg Clear News"]:
        return "tools_news" if state.messages[-1].tool_calls else "Msg Clear News"

    def should_continue_fundamentals(
        self, state: AgentState
    ) -> Literal["tools_fundamentals", "Msg Clear Fundamentals"]:
        return "tools_fundamentals" if state.messages[-1].tool_calls else "Msg Clear Fundamentals"

    def should_continue_debate(
        self, state: AgentState
    ) -> Literal["Bull Researcher", "Bear Researcher", "Research Manager"]:
        debate = state.investment_debate_state
        if debate.count >= 2 * self.max_debate_rounds:
            return "Research Manager"
        if debate.current_response.startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(
        self, state: AgentState
    ) -> Literal["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Risk Judge"]:
        risk = state.risk_debate_state
        if risk.count >= 3 * self.max_risk_discuss_rounds:
            return "Risk Judge"
        if risk.latest_speaker.startswith("Aggressive"):
            return "Conservative Analyst"
        if risk.latest_speaker.startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
