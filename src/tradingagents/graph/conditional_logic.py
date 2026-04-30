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
        """Determine whether to continue market analysis or clear messages.

        Args:
            state (AgentState): The current state of the agent.

        Returns:
            Literal["tools_market", "Msg Clear Market"]: Next node to execute.
        """
        return "tools_market" if state.messages[-1].tool_calls else "Msg Clear Market"

    def should_continue_social(
        self, state: AgentState
    ) -> Literal["tools_social", "Msg Clear Social"]:
        """Determine whether to continue social media analysis or clear messages.

        Args:
            state (AgentState): The current state of the agent.

        Returns:
            Literal["tools_social", "Msg Clear Social"]: Next node to execute.
        """
        return "tools_social" if state.messages[-1].tool_calls else "Msg Clear Social"

    def should_continue_news(self, state: AgentState) -> Literal["tools_news", "Msg Clear News"]:
        """Determine whether to continue news analysis or clear messages.

        Args:
            state (AgentState): The current state of the agent.

        Returns:
            Literal["tools_news", "Msg Clear News"]: Next node to execute.
        """
        return "tools_news" if state.messages[-1].tool_calls else "Msg Clear News"

    def should_continue_fundamentals(
        self, state: AgentState
    ) -> Literal["tools_fundamentals", "Msg Clear Fundamentals"]:
        """Determine whether to continue fundamentals analysis or clear messages.

        Args:
            state (AgentState): The current state of the agent.

        Returns:
            Literal["tools_fundamentals", "Msg Clear Fundamentals"]: Next node to execute.
        """
        return "tools_fundamentals" if state.messages[-1].tool_calls else "Msg Clear Fundamentals"

    def should_continue_debate(
        self, state: AgentState
    ) -> Literal["Bull Researcher", "Bear Researcher", "Research Manager"]:
        """Determine the next step in the investment debate.

        Args:
            state (AgentState): The current state of the agent.

        Returns:
            Literal["Bull Researcher", "Bear Researcher", "Research Manager"]: Next node to execute.
        """
        debate = state.investment_debate_state
        if debate.count >= 2 * self.max_debate_rounds:
            return "Research Manager"
        if debate.current_response.startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(
        self, state: AgentState
    ) -> Literal["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Risk Judge"]:
        """Determine the next step in the risk analysis debate.

        Args:
            state (AgentState): The current state of the agent.

        Returns:
            Literal["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Risk Judge"]: Next node to execute.
        """
        risk = state.risk_debate_state
        if risk.count >= 3 * self.max_risk_discuss_rounds:
            return "Risk Judge"
        if risk.latest_speaker.startswith("Aggressive"):
            return "Conservative Analyst"
        if risk.latest_speaker.startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
