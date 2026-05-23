from typing import Any
from collections.abc import Callable

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.agent_states import AgentState


def create_situation_summariser(llm: ChatModel) -> Callable[[AgentState], dict[str, Any]]:
    def situation_summariser_node(state: AgentState) -> dict[str, Any]:
        prompt = load_prompt("situation_summariser").format(
            ticker=state.company_of_interest,
            current_date=state.trade_date,
            market_research_report=state.market_report,
            sentiment_report=state.sentiment_report,
            news_report=state.news_report,
            fundamentals_report=state.fundamentals_report,
        )
        response = llm.invoke(prompt)
        content = response.content
        if isinstance(content, list):
            content = "\n".join(
                item.get("text", "") if isinstance(item, dict) else str(item) for item in content
            )
        return {"situation_summary": str(content)}

    return situation_summariser_node
