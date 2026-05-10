from typing import Any
from collections.abc import Callable

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.risk_mgmt._helpers import first_turn_or
from tradingagents.agents.utils.agent_states import AgentState, RiskDebateState


def create_neutral_debator(llm: ChatModel) -> Callable[[AgentState], dict[str, Any]]:
    """Creates a neutral risk debator node for the trading graph.

    Args:
        llm (ChatModel): The language model to use for generating responses.

    Returns:
        Callable[[AgentState], dict[str, Any]]: A function representing the neutral risk debator node.
    """

    def neutral_node(state: AgentState) -> dict[str, Any]:
        """Executes the neutral debator logic to provide a neutral risk perspective.

        Args:
            state (AgentState): The current state of the agent, including reports, plan, and risk state.

        Returns:
            dict[str, Any]: A dictionary containing the updated risk_debate_state.
        """
        risk = state.risk_debate_state

        prompt = load_prompt("neutral_debator").format(
            trader_decision=state.trader_investment_plan,
            market_research_report=state.market_report,
            sentiment_report=state.sentiment_report,
            news_report=state.news_report,
            fundamentals_report=state.fundamentals_report,
            history=risk.history,
            current_aggressive_response=first_turn_or(risk.current_aggressive_response),
            current_conservative_response=first_turn_or(risk.current_conservative_response),
        )

        response = llm.invoke(prompt)
        argument = f"Neutral Analyst: {response.content}"

        new_risk_state = RiskDebateState(
            history=risk.history + "\n" + argument,
            aggressive_history=risk.aggressive_history,
            conservative_history=risk.conservative_history,
            neutral_history=risk.neutral_history + "\n" + argument,
            latest_speaker="Neutral",
            current_aggressive_response=risk.current_aggressive_response,
            current_conservative_response=risk.current_conservative_response,
            current_neutral_response=argument,
            count=risk.count + 1,
        )

        return {"risk_debate_state": new_risk_state}

    return neutral_node
