from typing import Any
from collections.abc import Callable

from tradingagents.llm import ChatModel

from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import AgentState, InvestDebateState


def create_research_manager(
    llm: ChatModel, memory: FinancialSituationMemory
) -> Callable[[AgentState], dict[str, Any]]:
    def research_manager_node(state: AgentState) -> dict[str, Any]:
        debate = state.investment_debate_state

        curr_situation = (
            f"{state.market_report}\n\n"
            f"{state.sentiment_report}\n\n"
            f"{state.news_report}\n\n"
            f"{state.fundamentals_report}"
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = "".join(rec["recommendation"] + "\n\n" for rec in past_memories)

        prompt = load_prompt("research_manager").format(
            past_memory_str=past_memory_str, history=debate.history
        )
        response = llm.invoke(prompt)

        new_debate_state = InvestDebateState(
            judge_decision=response.content,
            history=debate.history,
            bear_history=debate.bear_history,
            bull_history=debate.bull_history,
            current_response=response.content,
            count=debate.count,
        )

        return {"investment_debate_state": new_debate_state, "investment_plan": response.content}

    return research_manager_node
