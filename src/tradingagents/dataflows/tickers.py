"""Ticker normalization helpers for Yahoo Finance backed dataflows."""

import logging
from functools import lru_cache

import yfinance as yf

logger = logging.getLogger(__name__)

TAIWAN_SUFFIXES = (".TW", ".TWO")
SEARCH_QUOTE_TYPES = {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}
US_SHARE_CLASS_SUFFIXES = {"A", "B", "C", "K", "U", "V"}

# Map yfinance suffixes to Google News (hl, gl, ceid) triplets.
# The default is en-US for US tickers; foreign exchanges get their local
# language so small-cap issuers without English coverage are not blacked
# out of the news pipeline.
_REGION_BY_SUFFIX: dict[str, tuple[str, str, str]] = {
    ".TW": ("zh-TW", "TW", "TW:zh-Hant"),
    ".TWO": ("zh-TW", "TW", "TW:zh-Hant"),
    ".T": ("ja-JP", "JP", "JP:ja"),
    ".HK": ("zh-HK", "HK", "HK:zh-Hant"),
    ".SS": ("zh-CN", "CN", "CN:zh-Hans"),
    ".SZ": ("zh-CN", "CN", "CN:zh-Hans"),
    ".DE": ("de-DE", "DE", "DE:de"),
    ".F": ("de-DE", "DE", "DE:de"),
    ".KS": ("ko-KR", "KR", "KR:ko"),
    ".KQ": ("ko-KR", "KR", "KR:ko"),
    ".L": ("en-GB", "GB", "GB:en"),
    ".PA": ("fr-FR", "FR", "FR:fr"),
    ".AS": ("nl-NL", "NL", "NL:nl"),
    ".AX": ("en-AU", "AU", "AU:en"),
    ".TO": ("en-CA", "CA", "CA:en"),
    ".V": ("en-CA", "CA", "CA:en"),
}
_DEFAULT_NEWS_LOCALE: tuple[str, str, str] = ("en-US", "US", "US:en")


def get_news_locale(symbol: str) -> tuple[str, str, str]:
    """Resolve Google News (hl, gl, ceid) parameters for a Yahoo Finance symbol.

    The Google News RSS endpoint accepts ``hl`` (host language),
    ``gl`` (geographical location), and ``ceid`` (country edition id);
    keeping them aligned with the issuer's home exchange is what makes
    small-cap foreign issuers actually surface in the news feed instead
    of returning only US-targeted English coverage.

    Args:
        symbol: A yfinance-style ticker, optionally with a known
            exchange suffix (``2330.TW``, ``7203.T``, ``ASML.AS``, ...).

    Returns:
        ``(hl, gl, ceid)``. Falls back to en-US for bare US-style
        symbols, unsuffixed digits, or unrecognised suffixes.
    """
    cleaned = symbol.strip().upper()
    if "." not in cleaned:
        return _DEFAULT_NEWS_LOCALE
    suffix = "." + cleaned.rsplit(".", 1)[-1]
    return _REGION_BY_SUFFIX.get(suffix, _DEFAULT_NEWS_LOCALE)


def _dedupe_symbols(symbols: tuple[str, ...]) -> list[str]:
    """Remove duplicate symbols from a tuple while preserving order.

    Args:
        symbols: Ticker symbols.

    Returns:
        Deduplicated list of ticker symbols.
    """
    return list(dict.fromkeys(symbols))


@lru_cache(maxsize=256)
def _search_yfinance_symbols_cached(query: str, limit: int) -> tuple[str, ...]:
    """Cached Yahoo Finance symbol search returning an immutable tuple."""
    try:
        search = yf.Search(query=query, max_results=limit, news_count=0, enable_fuzzy_query=True)
    except Exception:
        logger.debug("Failed to search Yahoo Finance for %s", query, exc_info=True)
        return ()

    symbols: list[str] = []
    for quote in search.quotes[:limit]:
        symbol = quote.get("symbol")
        quote_type = quote.get("quoteType")
        if symbol and (quote_type is None or quote_type.upper() in SEARCH_QUOTE_TYPES):
            symbols.append(symbol.upper())
    return tuple(symbols)


def _search_yfinance_symbols(query: str, limit: int = 5) -> list[str]:
    """Search Yahoo Finance for ticker symbols matching a query.

    Results are memoized per-process (LRU 256) because the analyst
    tool-loop may resolve the same ticker many times within one run, and
    Yahoo Finance Search rate-limits aggressively.

    Args:
        query: The search query.
        limit: Maximum number of results to return.

    Returns:
        Matching ticker symbols.
    """
    return list(_search_yfinance_symbols_cached(query, limit))


def _is_clean_us_alpha_symbol(symbol: str) -> bool:
    """Return whether a symbol is a clean US-style alpha ticker (1-5 chars).

    Such symbols (`AAPL`, `MSFT`, `BRK-B`, `TSLA`) are accepted directly by
    Yahoo Finance and do not need to be resolved through `yf.Search`. Skipping
    the search saves rate-limit budget on every analyst tool call.
    """
    bare = symbol.replace("-", "")
    return 1 <= len(bare) <= 5 and bare.isalpha()


def get_yfinance_symbol_candidates(symbol: str) -> list[str]:
    """Return Yahoo Finance ticker candidates for a user-supplied symbol.

    Explicit Yahoo Finance symbols such as `AAPL`, `TSM`, or `2330.TW` are
    accepted directly. Ambiguous bare symbols (digit-only, mixed) are resolved
    by Yahoo Finance Search, so Taiwan stock codes like `2330` and `8069` can
    be passed without suffixes.

    Args:
        symbol: The symbol to find candidates for.

    Returns:
        Candidate ticker symbols.

    Raises:
        ValueError: If the ticker symbol is empty.
    """
    raw_symbol = symbol.strip()
    if not raw_symbol:
        raise ValueError("Ticker symbol cannot be empty.")

    if ":" in raw_symbol:
        _, raw_symbol = raw_symbol.split(":", 1)
        raw_symbol = raw_symbol.strip()

    yahoo_symbol = raw_symbol.upper()
    if "." in yahoo_symbol:
        candidates: list[str] = [yahoo_symbol]
        suffix = yahoo_symbol.rsplit(".", 1)[-1]
        # Yahoo's `.→-` substitution is only valid for US share-class tickers
        # (BRK.B → BRK-B). Foreign suffixes like .T, .DE, .HK, .L should not
        # be rewritten — doing so produces a dead candidate that wastes a
        # request and risks rate-limit hits.
        if suffix in US_SHARE_CLASS_SUFFIXES:
            candidates.append(yahoo_symbol.replace(".", "-"))
        return _dedupe_symbols(tuple(candidates))

    if _is_clean_us_alpha_symbol(yahoo_symbol):
        return [yahoo_symbol]

    candidates = []
    candidates.extend(_search_yfinance_symbols(raw_symbol))
    if yahoo_symbol.isdigit():
        candidates.extend(f"{yahoo_symbol}{suf}" for suf in TAIWAN_SUFFIXES)
    candidates.append(yahoo_symbol)

    return _dedupe_symbols(tuple(candidates))


def describe_symbol_candidates(symbol: str, candidates: list[str]) -> str:
    """Format attempted Yahoo Finance symbols for user-facing tool output.

    Args:
        symbol (str): The original symbol queried.
        candidates (list[str]): The list of candidates attempted.

    Returns:
        str: A comma-separated string of candidates or the single matching symbol.
    """
    if len(candidates) == 1 and candidates[0] == symbol.upper():
        return candidates[0]
    return candidates[0] if len(candidates) == 1 else ", ".join(candidates)
