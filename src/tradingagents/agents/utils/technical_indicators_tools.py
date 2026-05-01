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
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-MM-DD"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """Retrieve technical indicators for a given ticker symbol.

    Args:
        symbol (str): Stock ticker, company symbol, or Taiwan stock code.
            Examples: AAPL, TSM, 2330.TW, 2330, 8069.
        indicator (str | list[str]): One or more technical indicators. May be a
            single indicator name, a Python list of names, or a comma-separated
            string like "macd,rsi,close_50_sma".
        curr_date (str): The current trading date in YYYY-MM-DD format.
        look_back_days (int, optional): Number of days to look back. Defaults
            to 30.

    Returns:
        str: A formatted report for one indicator, or multiple sections when
            several indicators are requested.

    Raises:
        ValueError: If no valid indicators are provided, an indicator is
            unsupported, or no market data is available for the symbol.
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
