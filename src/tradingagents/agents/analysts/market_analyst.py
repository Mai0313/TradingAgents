from typing import Any
from collections.abc import Callable

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.agent_utils import get_indicators, get_stock_data
from tradingagents.agents.utils.agent_states import AgentState


def create_market_analyst(llm: ChatModel) -> Callable[[AgentState], dict[str, Any]]:

    def market_analyst_node(state: AgentState) -> dict[str, Any]:
        tools = [get_stock_data, get_indicators]

        prompt = ChatPromptTemplate.from_messages([
            ("system", load_prompt("market_analyst")),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=state.trade_date)
        prompt = prompt.partial(ticker=state.company_of_interest)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state.messages)

        report = "" if result.tool_calls else result.content

        return {"messages": [result], "market_report": report}

    return market_analyst_node
