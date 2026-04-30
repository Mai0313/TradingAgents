from typing import Any
from collections.abc import Callable

from tradingagents.llm import ChatModel

from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import AgentState


def create_trader(
    llm: ChatModel, memory: FinancialSituationMemory
) -> Callable[[AgentState], dict[str, Any]]:
    def trader_node(state: AgentState) -> dict[str, Any]:
        curr_situation = (
            f"{state.market_report}\n\n"
            f"{state.sentiment_report}\n\n"
            f"{state.news_report}\n\n"
            f"{state.fundamentals_report}"
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        if past_memories:
            past_memory_str = "".join(rec["recommendation"] + "\n\n" for rec in past_memories)
        else:
            past_memory_str = "No past memories found."

        messages = [
            {
                "role": "system",
                "content": load_prompt("trader_system").format(past_memory_str=past_memory_str),
            },
            {
                "role": "user",
                "content": load_prompt("trader_user").format(
                    company_name=state.company_of_interest, investment_plan=state.investment_plan
                ),
            },
        ]

        result = llm.invoke(messages)

        return {"messages": [result], "trader_investment_plan": result.content}

    return trader_node
