"""Situation Summariser node — distils the four analyst reports into a
compact snapshot used as the BM25 retrieval query for every downstream
``memory.get_memories(...)`` call.
"""

from typing import Any
from collections.abc import Callable

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.agent_states import AgentState


def create_situation_summariser(llm: ChatModel) -> Callable[[AgentState], dict[str, Any]]:
    """Build the Situation Summariser LangGraph node.

    The summariser runs once between the last analyst's Msg Clear and the
    Bull Researcher entry. Its single output is ``state.situation_summary``,
    which every researcher / manager / trader / risk-judge then uses as the
    BM25 query against their respective memory store — much sharper signal
    than concatenating the four full reports (10-20 KB).

    Args:
        llm: ChatModel used to produce the snapshot.

    Returns:
        A LangGraph node callable conforming to
        ``(state: AgentState) -> dict[str, Any]``.
    """

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
