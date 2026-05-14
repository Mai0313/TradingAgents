from typing import Any
from collections.abc import Callable

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.memory import FinancialSituationMemory, format_memories_for_prompt
from tradingagents.agents.utils.agent_states import AgentState, InvestDebateState


def create_bear_researcher(
    llm: ChatModel, memory: FinancialSituationMemory
) -> Callable[[AgentState], dict[str, Any]]:
    """Creates a bear researcher node for the trading graph.

    Args:
        llm (ChatModel): The language model to use for generating responses.
        memory (FinancialSituationMemory): The memory module for retrieving past financial situations.

    Returns:
        Callable[[AgentState], dict[str, Any]]: A function representing the bear researcher node.
    """

    def bear_node(state: AgentState) -> dict[str, Any]:
        """Executes the bear researcher logic to formulate a bearish investment argument.

        Args:
            state (AgentState): The current state of the agent, including reports and the debate state.

        Returns:
            dict[str, Any]: A dictionary containing the updated investment_debate_state.
        """
        debate = state.investment_debate_state

        past_memories = memory.get_memories(
            state.situation_summary or state.combined_reports, n_matches=2
        )
        past_memory_str = format_memories_for_prompt(past_memories)

        prompt = load_prompt("bear_researcher").format(
            market_research_report=state.market_report,
            sentiment_report=state.sentiment_report,
            news_report=state.news_report,
            fundamentals_report=state.fundamentals_report,
            history=debate.history,
            current_response=debate.current_response,
            past_memory_str=past_memory_str,
        )

        response = llm.invoke(prompt)
        argument = f"Bear Analyst: {response.content}"

        new_debate_state = InvestDebateState(
            history=debate.history + "\n" + argument,
            bull_history=debate.bull_history,
            bear_history=debate.bear_history + "\n" + argument,
            current_response=argument,
            judge_decision=debate.judge_decision,
            count=debate.count + 1,
        )

        return {"investment_debate_state": new_debate_state}

    return bear_node
