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
        pub_date_str = content.get("pubDate", "")
        pub_date = None
        if pub_date_str:
            with contextlib.suppress(ValueError, AttributeError):
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))

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
        "pub_date": None,
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

    for candidate in candidates:
        try:
            stock = yf.Ticker(candidate)
            candidate_news = stock.get_news(count=20)
        except Exception:
            logger.debug("Failed to fetch news for %s", candidate, exc_info=True)
            continue
        if candidate_news:
            return candidate, candidate_news, candidates

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
        resolved_ticker, news, candidates = _get_first_ticker_news(ticker)

        if not news:
            tried = describe_symbol_candidates(ticker, candidates)
            return f"No news found for {ticker} (tried: {tried})"

        # Parse date range for filtering
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        news_str = ""
        filtered_count = 0

        for article in news:
            data = _extract_article_data(article)

            # Filter by date if publish time is available
            if data["pub_date"]:
                pub_date_naive = data["pub_date"].replace(tzinfo=None)
                if not (start_dt <= pub_date_naive <= end_dt + relativedelta(days=1)):
                    continue

            news_str += f"### {data['title']} (source: {data['publisher']})\n"
            if data["summary"]:
                news_str += f"{data['summary']}\n"
            if data["link"]:
                news_str += f"Link: {data['link']}\n"
            news_str += "\n"
            filtered_count += 1

        if filtered_count == 0:
            return f"No news found for {resolved_ticker} between {start_date} and {end_date}"

        return f"## {resolved_ticker} News, from {start_date} to {end_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching news for {ticker}: {e!s}"


def _format_article_to_str(article: dict) -> str:
    """Format a news article dict into a display string.

    Args:
        article (dict): The article data dictionary.

    Returns:
        str: A formatted string representation of the article.
    """
    if "content" in article:
        data = _extract_article_data(article)
        title = data["title"]
        publisher = data["publisher"]
        link = data["link"]
        summary = data["summary"]
    else:
        title = article.get("title", "No title")
        publisher = article.get("publisher", "Unknown")
        link = article.get("link", "")
        summary = ""

    result = f"### {title} (source: {publisher})\n"
    if summary:
        result += f"{summary}\n"
    if link:
        result += f"Link: {link}\n"
    return result + "\n"


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
    search_queries = [
        "global stock market economy",
        "interest rates inflation economic outlook",
        "Asia markets trading",
        "semiconductor supply chain market outlook",
        "global markets trading",
    ]

    all_news: list[dict] = []
    seen_titles: set[str] = set()

    try:
        for query in search_queries:
            search = yf.Search(query=query, news_count=limit, enable_fuzzy_query=True)

            if search.news:
                for article in search.news:
                    # Handle both flat and nested structures
                    data = _extract_article_data(article) if "content" in article else article
                    title = data.get("title", "")

                    # Deduplicate by title
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        all_news.append(article)

            if len(all_news) >= limit:
                break

        if not all_news:
            return f"No global news found for {curr_date}"

        # Calculate date range
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - relativedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        news_str = "".join(_format_article_to_str(article) for article in all_news[:limit])

        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching global news: {e!s}"
