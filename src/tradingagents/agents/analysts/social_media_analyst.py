from typing import Any
from collections.abc import Callable

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.agent_utils import get_news
from tradingagents.agents.utils.agent_states import AgentState


def create_social_media_analyst(llm: ChatModel) -> Callable[[AgentState], dict[str, Any]]:
    """Creates a social media analyst node for the trading graph.

    Args:
        llm (ChatModel): The language model to use for generating responses.

    Returns:
        Callable[[AgentState], dict[str, Any]]: A function representing the social media analyst node.
    """
    def social_media_analyst_node(state: AgentState) -> dict[str, Any]:
        """Executes the social media analyst logic to generate a sentiment report.

        Args:
            state (AgentState): The current state of the agent, containing data like trade_date and company_of_interest.

        Returns:
            dict[str, Any]: A dictionary containing updated messages and the sentiment_report.
        """
        tools = [get_news]

        prompt = ChatPromptTemplate.from_messages([
            ("system", load_prompt("social_media_analyst")),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=state.trade_date)
        prompt = prompt.partial(ticker=state.company_of_interest)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state.messages)

        report = "" if result.tool_calls else result.content

        return {"messages": [result], "sentiment_report": report}

    return social_media_analyst_node
