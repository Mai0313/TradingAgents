from typing import Any
from collections.abc import Callable

from tradingagents.llm import ChatModel
from tradingagents.agents.risk_mgmt._helpers import make_debator_node
from tradingagents.agents.utils.agent_states import AgentState


def create_conservative_debator(llm: ChatModel) -> Callable[[AgentState], dict[str, Any]]:
    """Create the conservative risk-debator node for the trading graph."""
    return make_debator_node("Conservative", llm)
