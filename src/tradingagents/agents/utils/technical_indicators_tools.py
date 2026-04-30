from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.yfinance import get_stock_stats_indicators_window


@tool
def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[
        str | list[str],
        "One or more technical indicators. Accepts a single indicator name, a list of names, or a comma-separated string.",
    ],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """Retrieve technical indicators for a given ticker symbol.

    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        indicator (str | list[str]): One or more technical indicators. May be a
            single indicator name, a Python list of names, or a comma-separated
            string like "macd,rsi,close_50_sma".
        curr_date (str): The current trading date you are trading on, YYYY-mm-dd
        look_back_days (int): How many days to look back, default is 30
    Returns:
        str: A formatted report containing the technical indicators for the specified ticker symbol and indicator(s).
    """
    if isinstance(indicator, str):
        indicators = [ind.strip() for ind in indicator.split(",") if ind.strip()]
    else:
        indicators = [ind.strip() for ind in indicator if ind and ind.strip()]

    if not indicators:
        raise ValueError("At least one indicator must be provided.")

    if len(indicators) == 1:
        return get_stock_stats_indicators_window(symbol, indicators[0], curr_date, look_back_days)

    sections = []
    for ind in indicators:
        report = get_stock_stats_indicators_window(symbol, ind, curr_date, look_back_days)
        sections.append(f"## {ind}\n{report}")
    return "\n\n".join(sections)
