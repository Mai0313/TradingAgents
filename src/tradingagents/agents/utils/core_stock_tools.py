from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.yfinance import get_yfin_data_online


@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve stock price data (OHLCV) for a given ticker symbol.

    Args:
        symbol (str): Stock ticker, company symbol, or Taiwan stock code.
            Examples: AAPL, TSM, 2330.TW, 2330, 8069.
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format

    Returns:
        str: CSV-formatted OHLCV data with a short metadata header, or a
            no-data message if no Yahoo Finance candidate has price history.
    """
    return get_yfin_data_online(symbol, start_date, end_date)
