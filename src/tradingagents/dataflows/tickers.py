"""Ticker normalization helpers for Yahoo Finance backed dataflows."""

import logging

import yfinance as yf

logger = logging.getLogger(__name__)

TAIWAN_SUFFIXES = (".TW", ".TWO")
SEARCH_QUOTE_TYPES = {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}


def _dedupe_symbols(symbols: list[str]) -> list[str]:
    seen = set()
    result = []
    for symbol in symbols:
        if symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def _search_yfinance_symbols(query: str, limit: int = 5) -> list[str]:
    try:
        search = yf.Search(query=query, max_results=limit, news_count=0, enable_fuzzy_query=True)
    except Exception:
        logger.debug("Failed to search Yahoo Finance for %s", query, exc_info=True)
        return []

    symbols = []
    for quote in search.quotes[:limit]:
        symbol = quote.get("symbol")
        quote_type = quote.get("quoteType")
        if symbol and (quote_type is None or quote_type.upper() in SEARCH_QUOTE_TYPES):
            symbols.append(symbol.upper())

    return symbols


def get_yfinance_symbol_candidates(symbol: str) -> list[str]:
    """Return Yahoo Finance ticker candidates for a user supplied symbol.

    Explicit Yahoo Finance symbols such as `AAPL`, `TSM`, or `2330.TW` are
    accepted directly. Bare symbols are resolved by Yahoo Finance Search, so
    Taiwan stock codes like `2330` and `8069` can be passed without suffixes.
    """
    raw_symbol = symbol.strip()
    if not raw_symbol:
        raise ValueError("Ticker symbol cannot be empty.")

    if ":" in raw_symbol:
        _, raw_symbol = raw_symbol.split(":", 1)
        raw_symbol = raw_symbol.strip()

    yahoo_symbol = raw_symbol.upper()
    if "." in yahoo_symbol:
        return [yahoo_symbol]

    candidates = [*_search_yfinance_symbols(raw_symbol)]
    if yahoo_symbol.isdigit():
        candidates.extend(f"{yahoo_symbol}{suffix}" for suffix in TAIWAN_SUFFIXES)
    candidates.append(yahoo_symbol)

    return _dedupe_symbols(candidates)


def describe_symbol_candidates(symbol: str, candidates: list[str]) -> str:
    """Format attempted Yahoo Finance symbols for user-facing tool output."""
    if len(candidates) == 1 and candidates[0] == symbol.upper():
        return candidates[0]
    return ", ".join(candidates)
