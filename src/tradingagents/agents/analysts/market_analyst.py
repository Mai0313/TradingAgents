from typing import Any
from collections.abc import Callable

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models import BaseChatModel

from tradingagents.agents.utils.agent_utils import get_indicators, get_stock_data


def create_market_analyst(llm: BaseChatModel) -> Callable[[dict[str, Any]], dict[str, Any]]:

    def market_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [get_stock_data, get_indicators]

        system_message = (
            "You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:\n\n"
            "Moving Averages:\n"
            "- close_50_sma: 50 SMA: A medium-term trend indicator.\n"
            "- close_200_sma: 200 SMA: A long-term trend benchmark.\n"
            "- close_10_ema: 10 EMA: A responsive short-term average.\n\n"
            "MACD Related:\n"
            "- macd: MACD: Computes momentum via differences of EMAs.\n"
            "- macds: MACD Signal: An EMA smoothing of the MACD line.\n"
            "- macdh: MACD Histogram: Shows the gap between the MACD line and its signal.\n\n"
            "Momentum Indicators:\n"
            "- rsi: RSI: Measures momentum to flag overbought/oversold conditions.\n\n"
            "Volatility Indicators:\n"
            "- boll: Bollinger Middle Band.\n"
            "- boll_ub: Bollinger Upper Band.\n"
            "- boll_lb: Bollinger Lower Band.\n"
            "- atr: ATR: Averages true range to measure volatility.\n\n"
            "Volume-Based Indicators:\n"
            "- vwma: VWMA: A moving average weighted by volume.\n\n"
            "Select indicators that provide diverse and complementary information. Avoid redundancy. "
            "Please make sure to call get_stock_data first to retrieve the CSV, then use get_indicators. "
            "Write a very detailed and nuanced report. Do not simply state the trends are mixed. "
            "Make sure to append a Markdown table at the end of the report."
        )

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " Use the provided tools to progress towards answering the question."
                " If you are unable to fully answer, that's OK; another assistant with different tools"
                " will help where you left off. Execute what you can to make progress."
                " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                " You have access to the following tools: {tool_names}.\n{system_message}"
                "For your reference, the current date is {current_date}. The company we want to look at is {ticker}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {"messages": [result], "market_report": report}

    return market_analyst_node
