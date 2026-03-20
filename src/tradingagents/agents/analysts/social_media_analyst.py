from typing import Any
from collections.abc import Callable

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models import BaseChatModel

from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.agent_utils import get_news
from tradingagents.agents.utils.agent_states import AgentState


def create_social_media_analyst(llm: BaseChatModel) -> Callable[[AgentState], dict[str, Any]]:
    def social_media_analyst_node(state: AgentState) -> dict[str, Any]:
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
