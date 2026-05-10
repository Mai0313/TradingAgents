"""News-fetching functions with yfinance + Google News RSS fallback."""

import logging
from datetime import datetime
import contextlib
from email.utils import parsedate_to_datetime
import urllib.parse

import yfinance as yf
import feedparser
from dateutil.relativedelta import relativedelta

from tradingagents.dataflows.tickers import (
    describe_symbol_candidates,
    get_yfinance_symbol_candidates,
)

logger = logging.getLogger(__name__)

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
_TOOL_ERROR_PREFIX = "[TOOL_ERROR]"
_NO_DATA_PREFIX = "[NO_DATA]"


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
        # RFC-2822 / email-style fallback ("Mon, 13 Jan 2025 10:30:00 GMT")
        with contextlib.suppress(Exception):
            return parsedate_to_datetime(value).replace(tzinfo=None)
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

    Note: yfinance returns only the ~50 most recent articles regardless of
    the date range, so back-dated runs typically yield no results. Callers
    that need historical coverage should use :func:`fetch_news` which
    falls back to Google News RSS.

    Args:
        ticker (str): Stock ticker symbol, such as "AAPL".
        start_date (str): Start date in YYYY-MM-DD format.
        end_date (str): End date in YYYY-MM-DD format.

    Returns:
        str: A formatted news report, a no-data message (prefixed with
        ``[NO_DATA]``), or an error message (prefixed with ``[TOOL_ERROR]``).
    """
    try:
        return _get_news_yfinance(ticker, start_date, end_date)
    except Exception as exc:
        logger.debug("Failed to fetch news for %s", ticker, exc_info=True)
        return f"{_TOOL_ERROR_PREFIX} Failed fetching yfinance news for {ticker}: {exc!s}"


def _get_news_yfinance(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve news for a ticker, raising errors for the public wrapper."""
    resolved_ticker, news, candidates = _get_first_ticker_news(ticker)

    if not news:
        tried = describe_symbol_candidates(ticker, candidates)
        return f"{_NO_DATA_PREFIX} No yfinance news found for {ticker} (tried: {tried})"

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
        if not (start_dt <= pub_date_naive < end_dt + relativedelta(days=1)):
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
            f"{_NO_DATA_PREFIX} No dated yfinance news for {resolved_ticker} "
            f"between {start_date} and {end_date}. (yfinance only exposes "
            f"~50 most recent articles; back-dated runs typically miss this window. "
            f"Skipped {skipped_undated} undated articles to avoid lookahead bias.)"
        )

    return f"## {resolved_ticker} News (yfinance), from {start_date} to {end_date}:\n\n{news_str}"


def _entry_publisher(entry: object) -> str:
    """Extract publisher name from a feedparser entry, with fallback."""
    source = getattr(entry, "source", None)
    if source:
        title = source.get("title") if isinstance(source, dict) else getattr(source, "title", None)
        if title:
            return str(title)
    return "Google News"


def _entry_pub_date(entry: object) -> datetime | None:
    """Extract a naive UTC datetime from a feedparser entry."""
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        with contextlib.suppress(TypeError, ValueError):
            return datetime(*parsed[:6])
    raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
    return _parse_pub_date(raw) if raw else None


def get_news_google_rss(ticker: str, start_date: str, end_date: str, limit: int = 30) -> str:
    """Retrieve ticker news from Google News RSS within a date window.

    Useful as a fallback to yfinance, which only returns the ~50 most
    recent articles regardless of the requested date range. Google News
    RSS reaches further into history (typically 2-4 weeks for free
    queries; longer with explicit date filters).

    Args:
        ticker (str): Stock ticker symbol, such as "AAPL".
        start_date (str): Start date in YYYY-MM-DD format.
        end_date (str): End date in YYYY-MM-DD format.
        limit (int, optional): Maximum number of articles to keep after
            date filtering. Defaults to 30.

    Returns:
        str: A formatted news report, a no-data message, or an error message.
    """
    try:
        start_dt = _parse_yyyy_mm_dd(start_date, "start_date")
        end_dt = _parse_yyyy_mm_dd(end_date, "end_date")
        if start_dt > end_dt:
            raise ValueError(
                f"start_date must be on or before end_date: {start_date} > {end_date}"
            )

        query = urllib.parse.quote_plus(f"{ticker} stock")
        url = _GOOGLE_NEWS_RSS.format(query=query)
        feed = feedparser.parse(url)
    except Exception as exc:
        logger.debug("Failed to fetch Google News RSS for %s", ticker, exc_info=True)
        return f"{_TOOL_ERROR_PREFIX} Google News RSS fetch failed for {ticker}: {exc!s}"

    entries = list(getattr(feed, "entries", []) or [])
    if not entries:
        return f"{_NO_DATA_PREFIX} No Google News results for {ticker}"

    news_str = ""
    kept = 0
    for entry in entries:
        pub_date = _entry_pub_date(entry)
        if pub_date is None:
            continue
        if not (start_dt <= pub_date < end_dt + relativedelta(days=1)):
            continue
        title = getattr(entry, "title", "(no title)")
        link = getattr(entry, "link", "")
        publisher = _entry_publisher(entry)
        news_str += f"### {title} (source: {publisher})\n"
        news_str += f"Published: {pub_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
        if link:
            news_str += f"Link: {link}\n"
        news_str += "\n"
        kept += 1
        if kept >= limit:
            break

    if kept == 0:
        return (
            f"{_NO_DATA_PREFIX} No Google News results for {ticker} between "
            f"{start_date} and {end_date}"
        )

    return f"## {ticker} News (Google News RSS), from {start_date} to {end_date}:\n\n{news_str}"


def fetch_news(ticker: str, start_date: str, end_date: str) -> str:
    """Combine yfinance and Google News RSS coverage for a ticker.

    Tries yfinance first, then Google News RSS. Returns whichever sources
    produced articles; if both are empty, returns a single combined
    no-data message so the calling LLM can decide how to proceed.
    """
    yf_result = get_news_yfinance(ticker, start_date, end_date)
    rss_result = get_news_google_rss(ticker, start_date, end_date)

    yf_has_articles = yf_result.lstrip().startswith("##")
    rss_has_articles = rss_result.lstrip().startswith("##")

    if yf_has_articles and rss_has_articles:
        return yf_result + "\n\n---\n\n" + rss_result
    if yf_has_articles:
        return yf_result
    if rss_has_articles:
        return rss_result
    # Both failed or empty -- combine the diagnostic messages so the LLM
    # sees both reasons rather than guessing.
    return f"{yf_result}\n\n{rss_result}"


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
            if not (start_dt <= pub_date_naive < end_dt + relativedelta(days=1)):
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
        return f"{_TOOL_ERROR_PREFIX} Failed fetching global news: {exc!s}"


_GLOBAL_NEWS_QUERIES = (
    "global stock market economy",
    "interest rates inflation economic outlook",
    "Asia semiconductor supply chain",
    "Taiwan stock market TAIEX",
    "China Japan Korea markets",
)


def _get_global_news_yfinance(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """Retrieve global news, raising errors for the public wrapper."""
    if look_back_days < 0:
        raise ValueError("look_back_days must be >= 0.")
    if limit <= 0:
        raise ValueError("limit must be > 0.")

    curr_dt = _parse_yyyy_mm_dd(curr_date, "curr_date")
    start_dt = curr_dt - relativedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    all_news, skipped_undated = _collect_global_news(
        list(_GLOBAL_NEWS_QUERIES), start_dt, curr_dt, limit
    )

    if not all_news:
        return (
            f"{_NO_DATA_PREFIX} No dated global news between {start_date} and {curr_date}. "
            f"Skipped {skipped_undated} undated articles to avoid lookahead bias."
        )

    news_str = "".join(_format_article_to_str(article) for article in all_news[:limit])

    return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"
