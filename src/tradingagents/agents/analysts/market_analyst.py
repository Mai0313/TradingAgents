from typing import Any
from collections.abc import Callable

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.tool_registry import get_analyst_tools, get_analyst_tool_names


def create_market_analyst(llm: ChatModel) -> Callable[[AgentState], dict[str, Any]]:
    """Creates a market analyst node for the trading graph.

    Args:
        llm (ChatModel): The language model to use for generating responses.

    Returns:
        Callable[[AgentState], dict[str, Any]]: A function representing the market analyst node.
    """

    def market_analyst_node(state: AgentState) -> dict[str, Any]:
        """Executes the market analyst logic to generate a market report.

        Args:
            state (AgentState): The current state of the agent, containing data like trade_date and company_of_interest.

        Returns:
            dict[str, Any]: A dictionary containing updated messages and the market_report.
        """
        tools = get_analyst_tools("market")

        prompt = ChatPromptTemplate.from_messages([
            ("system", load_prompt("market_analyst")),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(tool_names=get_analyst_tool_names("market"))
        prompt = prompt.partial(current_date=state.trade_date)
        prompt = prompt.partial(ticker=state.company_of_interest)

        chain = prompt | llm.bind_tools(list(tools))

        result = chain.invoke(state.messages)

        report = "" if result.tool_calls else result.content

        return {"messages": [result], "market_report": report}

    return market_analyst_node
