from typing import Any
from collections.abc import Callable

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.memory import FinancialSituationMemory, format_memories_for_prompt
from tradingagents.agents.utils.agent_states import AgentState, RiskDebateState


def create_risk_manager(
    llm: ChatModel, memory: FinancialSituationMemory
) -> Callable[[AgentState], dict[str, Any]]:
    """Creates a risk manager node for the trading graph.

    Args:
        llm (ChatModel): The language model to use for generating responses.
        memory (FinancialSituationMemory): The memory module for retrieving past financial situations.

    Returns:
        Callable[[AgentState], dict[str, Any]]: A function representing the risk manager node.
    """

    def risk_manager_node(state: AgentState) -> dict[str, Any]:
        """Executes the risk manager logic to evaluate risk and make a final trade decision.

        Args:
            state (AgentState): The current state of the agent, including reports, investment plan, and risk state.

        Returns:
            dict[str, Any]: A dictionary containing the updated risk_debate_state and the final_trade_decision.
        """
        risk = state.risk_debate_state

        past_memories = memory.get_memories(
            state.situation_summary or state.combined_reports, n_matches=2
        )
        past_memory_str = format_memories_for_prompt(past_memories)

        prompt = load_prompt("risk_manager").format(
            trader_plan=state.trader_investment_plan,
            past_memory_str=past_memory_str,
            history=risk.history,
            market_research_report=state.market_report,
            sentiment_report=state.sentiment_report,
            news_report=state.news_report,
            fundamentals_report=state.fundamentals_report,
        )

        response = llm.invoke(prompt)

        new_risk_state = RiskDebateState(
            judge_decision=response.content,
            history=risk.history,
            aggressive_history=risk.aggressive_history,
            conservative_history=risk.conservative_history,
            neutral_history=risk.neutral_history,
            latest_speaker="Judge",
            current_aggressive_response=risk.current_aggressive_response,
            current_conservative_response=risk.current_conservative_response,
            current_neutral_response=risk.current_neutral_response,
            count=risk.count,
        )

        return {"risk_debate_state": new_risk_state, "final_trade_decision": response.content}

    return risk_manager_node
