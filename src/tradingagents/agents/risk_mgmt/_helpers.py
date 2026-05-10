"""Shared helpers and the factory used by the three risk-debator nodes."""

from typing import Any, Literal
from collections.abc import Callable

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.agent_states import AgentState, RiskDebateState

_FIRST_TURN_SENTINEL = "(no response yet — you are the first speaker on this round)"

DebatorRole = Literal["Aggressive", "Conservative", "Neutral"]

_PEERS: dict[str, tuple[str, str]] = {
    "aggressive": ("conservative", "neutral"),
    "conservative": ("aggressive", "neutral"),
    "neutral": ("aggressive", "conservative"),
}


def first_turn_or(text: str) -> str:
    """Return ``text`` or an explicit first-speaker sentinel if it is empty.

    Risk-debate prompts splice in peers' previous responses via
    ``{current_*_response}`` placeholders. On the opening turn those values
    are empty strings, and LLMs frequently respond by inventing rebuttals to
    nonexistent prior arguments unless explicitly told the debate has not
    started yet.
    """
    return text or _FIRST_TURN_SENTINEL


def make_debator_node(role: DebatorRole, llm: ChatModel) -> Callable[[AgentState], dict[str, Any]]:
    """Build the LangGraph node for one of the three risk debators.

    The three previous per-role node implementations were 90% duplicate;
    this factory keeps a single source of truth for the prompt-format /
    state-update shape so adding a new field to :class:`RiskDebateState`
    or rewording a peer-response placeholder needs only one edit.

    Args:
        role: ``"Aggressive"``, ``"Conservative"``, or ``"Neutral"``.
        llm: ChatModel used to generate the debate response.

    Returns:
        A LangGraph node callable conforming to
        ``(state: AgentState) -> dict[str, Any]``.
    """
    role_lower = role.lower()
    if role_lower not in _PEERS:
        raise ValueError(f"Unknown debator role: {role!r}")
    peers = _PEERS[role_lower]
    prompt_name = f"{role_lower}_debator"

    def debator_node(state: AgentState) -> dict[str, Any]:
        risk = state.risk_debate_state

        prompt_kwargs: dict[str, str] = {
            "trader_decision": state.trader_investment_plan,
            "market_research_report": state.market_report,
            "sentiment_report": state.sentiment_report,
            "news_report": state.news_report,
            "fundamentals_report": state.fundamentals_report,
            "history": risk.history,
        }
        for peer in peers:
            attr = f"current_{peer}_response"
            prompt_kwargs[attr] = first_turn_or(getattr(risk, attr))

        prompt = load_prompt(prompt_name).format(**prompt_kwargs)
        response = llm.invoke(prompt)
        argument = f"{role} Analyst: {response.content}"

        own_history_attr = f"{role_lower}_history"
        update: dict[str, Any] = {
            "history": risk.history + "\n" + argument,
            "latest_speaker": role,
            "count": risk.count + 1,
            own_history_attr: getattr(risk, own_history_attr) + "\n" + argument,
            f"current_{role_lower}_response": argument,
        }
        for peer in peers:
            update[f"{peer}_history"] = getattr(risk, f"{peer}_history")
            update[f"current_{peer}_response"] = getattr(risk, f"current_{peer}_response")

        new_risk_state = RiskDebateState(**update)
        return {"risk_debate_state": new_risk_state}

    return debator_node
