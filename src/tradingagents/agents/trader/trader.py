from typing import Any
from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import AgentState


def create_trader(
    llm: ChatModel, memory: FinancialSituationMemory
) -> Callable[[AgentState], dict[str, Any]]:
    """Creates a trader node for the trading graph.

    Args:
        llm (ChatModel): The language model to use for generating responses.
        memory (FinancialSituationMemory): The memory module for retrieving past financial situations.

    Returns:
        Callable[[AgentState], dict[str, Any]]: A function representing the trader node.
    """

    def trader_node(state: AgentState) -> dict[str, Any]:
        """Executes the trader logic to evaluate the situation and make an investment plan.

        Args:
            state (AgentState): The current state of the agent, including reports and plans.

        Returns:
            dict[str, Any]: A dictionary containing updated messages and the trader_investment_plan.
        """
        past_memories = memory.get_memories(state.combined_reports, n_matches=2)
        if past_memories:
            past_memory_str = "".join(rec["recommendation"] + "\n\n" for rec in past_memories)
        else:
            past_memory_str = "No past memories found."

        messages = [
            SystemMessage(
                content=load_prompt("trader_system").format(past_memory_str=past_memory_str)
            ),
            HumanMessage(
                content=load_prompt("trader_user").format(
                    company_name=state.company_of_interest, investment_plan=state.investment_plan
                )
            ),
        ]

        result = llm.invoke(messages)

        return {"messages": [result], "trader_investment_plan": result.content}

    return trader_node
