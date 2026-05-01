from typing import Any
from collections.abc import Callable

from langchain_core.messages import HumanMessage, RemoveMessage

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_global_news,
    get_insider_transactions,
)

# Re-export tools for convenience
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fundamental_data_tools import (
    get_cashflow,
    get_fundamentals,
    get_balance_sheet,
    get_income_statement,
)
from tradingagents.agents.utils.technical_indicators_tools import get_indicators

__all__ = [
    "create_msg_delete",
    "get_balance_sheet",
    "get_cashflow",
    "get_fundamentals",
    "get_global_news",
    "get_income_statement",
    "get_indicators",
    "get_insider_transactions",
    "get_news",
    "get_stock_data",
]


def create_msg_delete() -> Callable[[AgentState], dict[str, Any]]:
    """Create a function that deletes messages from the agent state.

    Returns:
        Callable[[AgentState], dict[str, Any]]: A function that takes an AgentState
            and returns a dictionary with operations to remove existing messages
            and add a placeholder message.
    """

    def delete_messages(state: AgentState) -> dict[str, Any]:
        """Clear messages and add placeholder for Anthropic compatibility.

        Args:
            state (AgentState): The current state of the agent.

        Returns:
            dict[str, Any]: A dictionary containing the 'messages' key with a list
                of RemoveMessage operations and a placeholder HumanMessage.
        """
        removal_operations = [RemoveMessage(id=m.id) for m in state.messages]
        placeholder = HumanMessage(content="Continue")
        return {"messages": [*removal_operations, placeholder]}

    return delete_messages
