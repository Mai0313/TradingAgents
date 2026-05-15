from typing import Any
from collections.abc import Callable

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.tool_registry import get_analyst_tools, get_analyst_tool_names


def create_fundamentals_analyst(llm: ChatModel) -> Callable[[AgentState], dict[str, Any]]:
    """Creates a fundamentals analyst node for the trading graph.

    Args:
        llm (ChatModel): The language model to use for generating responses.

    Returns:
        Callable[[AgentState], dict[str, Any]]: A function representing the fundamentals analyst node.
    """

    def fundamentals_analyst_node(state: AgentState) -> dict[str, Any]:
        """Executes the fundamentals analyst logic to generate a fundamentals report.

        Args:
            state (AgentState): The current state of the agent, containing data like trade_date and company_of_interest.

        Returns:
            dict[str, Any]: A dictionary containing updated messages and the fundamentals_report.
        """
        tools = get_analyst_tools("fundamentals")

        prompt = ChatPromptTemplate.from_messages([
            ("system", load_prompt("fundamentals_analyst")),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(tool_names=get_analyst_tool_names("fundamentals"))
        prompt = prompt.partial(current_date=state.trade_date)
        prompt = prompt.partial(ticker=state.company_of_interest)

        chain = prompt | llm.bind_tools(list(tools))

        result = chain.invoke(state.messages)

        report = "" if result.tool_calls else result.content

        return {"messages": [result], "fundamentals_report": report}

    return fundamentals_analyst_node
