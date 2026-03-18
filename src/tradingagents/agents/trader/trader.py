from typing import Any
import functools
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel

from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.memory import FinancialSituationMemory


def create_trader(
    llm: BaseChatModel, memory: FinancialSituationMemory
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def trader_node(state: dict[str, Any], name: str) -> dict[str, Any]:
        company_name = state["company_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for _i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
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
                    company_name=company_name, investment_plan=investment_plan
                ),
            },
        ]

        result = llm.invoke(messages)

        return {"messages": [result], "trader_investment_plan": result.content, "sender": name}

    return functools.partial(trader_node, name="Trader")
