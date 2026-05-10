from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.news import fetch_news, get_global_news_yfinance
from tradingagents.dataflows.yfinance import get_insider_transactions as _get_insider_transactions


@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve news for a ticker from yfinance plus Google News RSS fallback.

    The combined report includes whichever sources returned articles. If
    both sources are empty, a single combined ``[NO_DATA]`` message is
    returned so the calling LLM sees both diagnostic reasons.

    Args:
        ticker (str): Ticker symbol.
        start_date (str): Start date in YYYY-MM-DD format.
        end_date (str): End date in YYYY-MM-DD format.

    Returns:
        str: A formatted news report, a ``[NO_DATA]`` message, or a
        ``[TOOL_ERROR]`` message.
    """
    return fetch_news(ticker, start_date, end_date)


@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """Retrieve global news data.

    Args:
        curr_date (str): Current date in YYYY-MM-DD format.
        look_back_days (int, optional): Number of days used for the report
            window label. Defaults to 7.
        limit (int, optional): Maximum number of articles to return. Defaults
            to 5.

    Returns:
        str: A formatted global news report, a no-data message, or an error message.
    """
    return get_global_news_yfinance(curr_date, look_back_days, limit)


@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str | None, "current date in yyyy-mm-dd format"] = None,
) -> str:
    """Retrieve insider transaction information about a company.

    Args:
        ticker (str): Ticker symbol of the company.
        curr_date (str | None, optional): Current trading date used as a
            point-in-time boundary. Defaults to None.

    Returns:
        str: CSV-formatted insider transaction data, a no-data message, or an
            error message.
    """
    return _get_insider_transactions(ticker, curr_date)
