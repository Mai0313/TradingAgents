from typing import Any
from collections.abc import Callable

from langchain_core.language_models import BaseChatModel

from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.agent_states import AgentState, RiskDebateState


def create_conservative_debator(llm: BaseChatModel) -> Callable[[AgentState], dict[str, Any]]:
    def conservative_node(state: AgentState) -> dict[str, Any]:
        risk = state.risk_debate_state

        prompt = load_prompt("conservative_debator").format(
            trader_decision=state.trader_investment_plan,
            market_research_report=state.market_report,
            sentiment_report=state.sentiment_report,
            news_report=state.news_report,
            fundamentals_report=state.fundamentals_report,
            history=risk.history,
            current_aggressive_response=risk.current_aggressive_response,
            current_neutral_response=risk.current_neutral_response,
        )

        response = llm.invoke(prompt)
        argument = f"Conservative Analyst: {response.content}"

        new_risk_state = RiskDebateState(
            history=risk.history + "\n" + argument,
            aggressive_history=risk.aggressive_history,
            conservative_history=risk.conservative_history + "\n" + argument,
            neutral_history=risk.neutral_history,
            latest_speaker="Conservative",
            current_aggressive_response=risk.current_aggressive_response,
            current_conservative_response=argument,
            current_neutral_response=risk.current_neutral_response,
            count=risk.count + 1,
        )

        return {"risk_debate_state": new_risk_state}

    return conservative_node
