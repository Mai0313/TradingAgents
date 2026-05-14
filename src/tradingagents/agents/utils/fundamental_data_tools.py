from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.yfinance import get_cashflow as _get_cashflow
from tradingagents.dataflows.yfinance import get_fundamentals as _get_fundamentals
from tradingagents.dataflows.yfinance import get_balance_sheet as _get_balance_sheet
from tradingagents.dataflows.yfinance import get_short_interest as _get_short_interest
from tradingagents.dataflows.yfinance import get_analyst_ratings as _get_analyst_ratings
from tradingagents.dataflows.yfinance import get_dividends_splits as _get_dividends_splits
from tradingagents.dataflows.yfinance import get_income_statement as _get_income_statement
from tradingagents.dataflows.yfinance import (
    get_institutional_holders as _get_institutional_holders,
)


@tool
def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve comprehensive fundamental data for a given ticker symbol.

    Args:
        ticker (str): Ticker symbol of the company.
        curr_date (str): Current trading date in YYYY-MM-DD format.

    Returns:
        str: A formatted report containing comprehensive fundamental data.
    """
    return _get_fundamentals(ticker, curr_date)


@tool
def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str | None, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve balance sheet data for a given ticker symbol.

    Args:
        ticker (str): Ticker symbol of the company.
        freq (str, optional): Reporting frequency, either annual or quarterly.
            Defaults to "quarterly".
        curr_date (str | None, optional): Current trading date in YYYY-MM-DD
            format. Defaults to None.

    Returns:
        str: A formatted report containing balance sheet data.
    """
    return _get_balance_sheet(ticker, freq, curr_date)


@tool
def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str | None, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve cash flow statement data for a given ticker symbol.

    Args:
        ticker (str): Ticker symbol of the company.
        freq (str, optional): Reporting frequency, either annual or quarterly.
            Defaults to "quarterly".
        curr_date (str | None, optional): Current trading date in YYYY-MM-DD
            format. Defaults to None.

    Returns:
        str: A formatted report containing cash flow statement data.
    """
    return _get_cashflow(ticker, freq, curr_date)


@tool
def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str | None, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve income statement data for a given ticker symbol.

    Args:
        ticker (str): Ticker symbol of the company.
        freq (str, optional): Reporting frequency, either annual or quarterly.
            Defaults to "quarterly".
        curr_date (str | None, optional): Current trading date in YYYY-MM-DD
            format. Defaults to None.

    Returns:
        str: A formatted report containing income statement data.
    """
    return _get_income_statement(ticker, freq, curr_date)


@tool
def get_analyst_ratings(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str | None, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve analyst rating counts (rolling history + current snapshot).

    Returns the rolling strong-buy / buy / hold / sell / strong-sell
    distribution by period plus, for present-day runs only, the
    recommendation summary. Historical runs see the rolling history
    filtered to periods on or before ``curr_date``.

    Args:
        ticker (str): Ticker symbol.
        curr_date (str | None, optional): Current trading date in
            YYYY-MM-DD format.

    Returns:
        str: Formatted ratings report, ``[NO_DATA]`` message, or
            ``[TOOL_ERROR]`` message.
    """
    return _get_analyst_ratings(ticker, curr_date)


@tool
def get_institutional_holders(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str | None, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve institutional + major holders snapshots.

    yfinance only exposes the current snapshot; for back-dated
    ``curr_date`` this tool deliberately returns ``[NO_DATA]`` to
    avoid leaking present-day positioning into historical analysis.

    Args:
        ticker (str): Ticker symbol.
        curr_date (str | None, optional): Current trading date in
            YYYY-MM-DD format.

    Returns:
        str: Formatted holders snapshot or ``[NO_DATA]`` message.
    """
    return _get_institutional_holders(ticker, curr_date)


@tool
def get_short_interest(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str | None, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve short interest, days-to-cover, and float percentage.

    Sourced from current ``yfinance.info``; historical ``curr_date`` is
    rejected with ``[NO_DATA]`` to keep back-tests lookahead-free.

    Args:
        ticker (str): Ticker symbol.
        curr_date (str | None, optional): Current trading date in
            YYYY-MM-DD format.

    Returns:
        str: Formatted short-interest report or ``[NO_DATA]`` message.
    """
    return _get_short_interest(ticker, curr_date)


@tool
def get_dividends_splits(
    ticker: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "end date in YYYY-MM-DD format"],
) -> str:
    """Retrieve dividends and stock-split events in the requested window.

    Both yfinance series are date-indexed history, so the returned
    rows are inherently point-in-time correct -- back-test cleanly by
    passing ``end_date == curr_date``.

    Args:
        ticker (str): Ticker symbol.
        start_date (str): Window start in YYYY-MM-DD format.
        end_date (str): Window end (inclusive) in YYYY-MM-DD format.

    Returns:
        str: Formatted dividends / splits report or ``[NO_DATA]`` message.
    """
    return _get_dividends_splits(ticker, start_date, end_date)
