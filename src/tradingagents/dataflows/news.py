"""yfinance-based news data fetching functions."""

import logging
from datetime import datetime
import contextlib

import yfinance as yf
from dateutil.relativedelta import relativedelta

from tradingagents.dataflows.tickers import (
    describe_symbol_candidates,
    get_yfinance_symbol_candidates,
)

logger = logging.getLogger(__name__)


def _parse_yyyy_mm_dd(value: str, field_name: str) -> datetime:
    """Parse a YYYY-MM-DD date string with a clear error."""
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format: {value!r}") from exc


def _parse_pub_date(value: object) -> datetime | None:
    """Parse known yfinance publish date shapes into a datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value)
    if isinstance(value, str):
        with contextlib.suppress(ValueError, AttributeError):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _extract_article_data(article: dict) -> dict:
    """Extract article fields from flat or nested yfinance news data.

    Args:
        article (dict): The article data dictionary from yfinance.

    Returns:
        dict: Extracted article data containing title, summary, publisher, link, and pub_date.
    """
    # Handle nested content structure
    if "content" in article:
        content = article["content"]
        title = content.get("title", "No title")
        summary = content.get("summary", "")
        provider = content.get("provider", {})
        publisher = provider.get("displayName", "Unknown")

        # Get URL from canonicalUrl or clickThroughUrl
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        link = url_obj.get("url", "")

        # Get publish date
        pub_date = _parse_pub_date(content.get("pubDate") or content.get("providerPublishTime"))

        return {
            "title": title,
            "summary": summary,
            "publisher": publisher,
            "link": link,
            "pub_date": pub_date,
        }
    # Fallback for flat structure
    return {
        "title": article.get("title", "No title"),
        "summary": article.get("summary", ""),
        "publisher": article.get("publisher", "Unknown"),
        "link": article.get("link", ""),
        "pub_date": _parse_pub_date(
            article.get("pubDate")
            or article.get("providerPublishTime")
            or article.get("publishTime")
        ),
    }


def _get_first_ticker_news(ticker: str) -> tuple[str, list[dict], list[str]]:
    """Fetch news from the first Yahoo Finance ticker candidate that has results.

    Args:
        ticker (str): The ticker symbol to search for.

    Returns:
        tuple[str, list[dict], list[str]]: A tuple containing the resolved ticker symbol,
            the list of news articles, and the list of tried candidate symbols.
    """
    candidates = get_yfinance_symbol_candidates(ticker)
    last_error: Exception | None = None
    fetched_any_candidate = False

    for candidate in candidates:
        try:
            stock = yf.Ticker(candidate)
            candidate_news = stock.get_news(count=50)
        except Exception as exc:
            logger.debug("Failed to fetch news for %s", candidate, exc_info=True)
            last_error = exc
            continue
        fetched_any_candidate = True
        if candidate_news:
            return candidate, candidate_news, candidates

    if not fetched_any_candidate and last_error is not None:
        tried = describe_symbol_candidates(ticker, candidates)
        raise RuntimeError(f"Failed to fetch news for {ticker} (tried: {tried})") from last_error

    return candidates[0], [], candidates


def get_news_yfinance(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve news for a specific stock ticker using yfinance.

    Args:
        ticker (str): Stock ticker symbol, such as "AAPL".
        start_date (str): Start date in YYYY-MM-DD format.
        end_date (str): End date in YYYY-MM-DD format.

    Returns:
        str: A formatted news report, a no-data message, or an error message.
    """
    try:
        return _get_news_yfinance(ticker, start_date, end_date)
    except Exception as exc:
        logger.debug("Failed to fetch news for %s", ticker, exc_info=True)
        return f"Error fetching news for {ticker}: {exc!s}"


def _get_news_yfinance(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve news for a ticker, raising errors for the public wrapper."""
    resolved_ticker, news, candidates = _get_first_ticker_news(ticker)

    if not news:
        tried = describe_symbol_candidates(ticker, candidates)
        return f"No news found for {ticker} (tried: {tried})"

    start_dt = _parse_yyyy_mm_dd(start_date, "start_date")
    end_dt = _parse_yyyy_mm_dd(end_date, "end_date")
    if start_dt > end_dt:
        raise ValueError(f"start_date must be on or before end_date: {start_date} > {end_date}")

    news_str = ""
    filtered_count = 0
    skipped_undated = 0

    for article in news:
        data = _extract_article_data(article)

        pub_date = data["pub_date"]
        if pub_date is None:
            skipped_undated += 1
            continue
        pub_date_naive = pub_date.replace(tzinfo=None)
        if not (start_dt <= pub_date_naive <= end_dt + relativedelta(days=1)):
            continue

        news_str += f"### {data['title']} (source: {data['publisher']})\n"
        news_str += f"Published: {pub_date_naive.strftime('%Y-%m-%d %H:%M:%S')}\n"
        if data["summary"]:
            news_str += f"{data['summary']}\n"
        if data["link"]:
            news_str += f"Link: {data['link']}\n"
        news_str += "\n"
        filtered_count += 1

    if filtered_count == 0:
        return (
            f"No dated news found for {resolved_ticker} between {start_date} and {end_date}. "
            f"Skipped {skipped_undated} undated articles to avoid lookahead bias."
        )

    return f"## {resolved_ticker} News, from {start_date} to {end_date}:\n\n{news_str}"


def _format_article_to_str(article: dict) -> str:
    """Format a news article dict into a display string.

    Args:
        article (dict): The article data dictionary.

    Returns:
        str: A formatted string representation of the article.
    """
    data = _extract_article_data(article)
    title = data["title"]
    publisher = data["publisher"]
    link = data["link"]
    summary = data["summary"]
    pub_date = data["pub_date"]

    result = f"### {title} (source: {publisher})\n"
    if pub_date:
        result += f"Published: {pub_date.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')}\n"
    if summary:
        result += f"{summary}\n"
    if link:
        result += f"Link: {link}\n"
    return result + "\n"


def _collect_global_news(
    search_queries: list[str], start_dt: datetime, end_dt: datetime, limit: int
) -> tuple[list[dict], int]:
    """Collect dated global news within a date window."""
    all_news: list[dict] = []
    seen_titles: set[str] = set()
    skipped_undated = 0
    last_error: Exception | None = None
    fetched_any_query = False

    for query in search_queries:
        try:
            search = yf.Search(query=query, news_count=limit, enable_fuzzy_query=True)
        except Exception as exc:
            logger.debug("Failed to fetch global news for query %s", query, exc_info=True)
            last_error = exc
            continue
        fetched_any_query = True
        for article in search.news or []:
            data = _extract_article_data(article)
            title = data.get("title", "")
            pub_date = data.get("pub_date")
            if pub_date is None:
                skipped_undated += 1
                continue
            pub_date_naive = pub_date.replace(tzinfo=None)
            if not (start_dt <= pub_date_naive <= end_dt + relativedelta(days=1)):
                continue
            if title and title not in seen_titles:
                seen_titles.add(title)
                all_news.append(article)

        if len(all_news) >= limit:
            break

    if not fetched_any_query and last_error is not None:
        raise RuntimeError(
            f"Failed to fetch global news from Yahoo Finance: {last_error!s}"
        ) from last_error

    return all_news, skipped_undated


def get_global_news_yfinance(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """Retrieve global/macro economic news using yfinance Search.

    Args:
        curr_date (str): Current date in YYYY-MM-DD format.
        look_back_days (int, optional): Number of days used for the report
            window label. Defaults to 7.
        limit (int, optional): Maximum number of articles to return. Defaults to 10.

    Returns:
        str: A formatted global news report, a no-data message, or an error message.
    """
    try:
        return _get_global_news_yfinance(curr_date, look_back_days, limit)
    except Exception as exc:
        logger.debug("Failed to fetch global news", exc_info=True)
        return f"Error fetching global news: {exc!s}"


def _get_global_news_yfinance(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """Retrieve global news, raising errors for the public wrapper."""
    search_queries = [
        "global stock market economy",
        "interest rates inflation economic outlook",
        "Asia markets trading",
        "semiconductor supply chain market outlook",
        "global markets trading",
        "Taiwan stock market TAIEX",
        "Taiwan economy export outlook",
        "Asia semiconductor industry",
        "China Hong Kong stock market",
        "Japan Korea stock market",
        "台股 加權指數",
        "亞洲股市 經濟",
    ]

    if look_back_days < 0:
        raise ValueError("look_back_days must be >= 0.")
    if limit <= 0:
        raise ValueError("limit must be > 0.")

    curr_dt = _parse_yyyy_mm_dd(curr_date, "curr_date")
    start_dt = curr_dt - relativedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    all_news, skipped_undated = _collect_global_news(search_queries, start_dt, curr_dt, limit)

    if not all_news:
        return (
            f"No dated global news found between {start_date} and {curr_date}. "
            f"Skipped {skipped_undated} undated articles to avoid lookahead bias."
        )

    news_str = "".join(_format_article_to_str(article) for article in all_news[:limit])

    return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"
