# TradingAgents/graph/conditional_logic.py

from typing import Literal

from pydantic import Field, BaseModel

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic(BaseModel):
    max_debate_rounds: int = Field(
        default=1, description="Maximum number of Bull/Bear investment debate rounds"
    )
    max_risk_discuss_rounds: int = Field(
        default=1, description="Maximum number of Risk debate rounds"
    )

    def should_continue_market(
        self, state: AgentState
    ) -> Literal["tools_market", "Msg Clear Market"]:
        messages = state["messages"]
        last_message = messages[-1]
        return "tools_market" if last_message.tool_calls else "Msg Clear Market"

    def should_continue_social(
        self, state: AgentState
    ) -> Literal["tools_social", "Msg Clear Social"]:
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState) -> Literal["tools_news", "Msg Clear News"]:
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(
        self, state: AgentState
    ) -> Literal["tools_fundamentals", "Msg Clear Fundamentals"]:
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    def should_continue_debate(
        self, state: AgentState
    ) -> Literal["Bull Researcher", "Bear Researcher", "Research Manager"]:
        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # 3 rounds of back-and-forth between 2 agents
            return "Research Manager"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(
        self, state: AgentState
    ) -> Literal["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Risk Judge"]:
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # 3 rounds of back-and-forth between 3 agents
            return "Risk Judge"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
