from typing import Any
from collections.abc import Callable

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models import BaseChatModel

from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.agent_utils import (
    get_cashflow,
    get_fundamentals,
    get_balance_sheet,
    get_income_statement,
)


def create_fundamentals_analyst(llm: BaseChatModel) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def fundamentals_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement]

        prompt = ChatPromptTemplate.from_messages([
            ("system", load_prompt("fundamentals_analyst")),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {"messages": [result], "fundamentals_report": report}

    return fundamentals_analyst_node
