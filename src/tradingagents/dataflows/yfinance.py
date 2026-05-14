from typing import Annotated
import logging
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from stockstats import wrap
from dateutil.relativedelta import relativedelta

from tradingagents.config import get_config
from tradingagents.dataflows.tickers import (
    get_news_locale,
    describe_symbol_candidates,
    get_yfinance_symbol_candidates,
)

logger = logging.getLogger(__name__)

_QUARTERLY_REPORTING_LAG_DAYS = 45
_ANNUAL_REPORTING_LAG_DAYS = 90


def _parse_yyyy_mm_dd(value: str, field_name: str) -> datetime:
    """Parse a YYYY-MM-DD date string with a field-specific error."""
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format: {value!r}") from exc


def _validate_date_range(start_date: str, end_date: str) -> tuple[datetime, datetime]:
    """Validate and parse an inclusive date range."""
    start_dt = _parse_yyyy_mm_dd(start_date, "start_date")
    end_dt = _parse_yyyy_mm_dd(end_date, "end_date")
    if start_dt > end_dt:
        raise ValueError(f"start_date must be on or before end_date: {start_date} > {end_date}")
    return start_dt, end_dt


def _normalize_freq(freq: str) -> str:
    """Normalize and validate a yfinance financial statement frequency."""
    normalized = freq.lower().strip()
    if normalized not in {"quarterly", "annual"}:
        raise ValueError("freq must be either 'quarterly' or 'annual'.")
    return normalized


def _as_of_datetime(curr_date: str | None) -> datetime | None:
    """Parse an optional current date used as a point-in-time boundary."""
    if curr_date is None:
        return None
    return _parse_yyyy_mm_dd(curr_date, "curr_date")


def _is_historical_date(curr_date: str | None) -> bool:
    """Return whether curr_date is before today's local date."""
    as_of = _as_of_datetime(curr_date)
    return as_of is not None and as_of.date() < datetime.now().date()


def _financial_statement_cutoff(curr_date: str | None, freq: str) -> pd.Timestamp | None:
    """Return the latest report period likely available by curr_date.

    Yahoo Finance exposes statement period end dates, not exact filing
    timestamps. For historical runs, use a conservative reporting lag so a
    trade date does not see a quarter or fiscal year that likely was not public
    yet.
    """
    as_of = _as_of_datetime(curr_date)
    if as_of is None:
        return None
    lag_days = (
        _QUARTERLY_REPORTING_LAG_DAYS
        if _normalize_freq(freq) == "quarterly"
        else _ANNUAL_REPORTING_LAG_DAYS
    )
    return pd.Timestamp(as_of - timedelta(days=lag_days))


def _filter_statement_as_of(data: pd.DataFrame, curr_date: str | None, freq: str) -> pd.DataFrame:
    """Filter financial statement columns to the as-of date boundary."""
    if data.empty or curr_date is None:
        return data

    cutoff = _financial_statement_cutoff(curr_date, freq)
    if cutoff is None:
        return data

    parsed_columns = pd.to_datetime(data.columns, errors="coerce")
    keep_columns = [
        column
        for column, parsed in zip(data.columns, parsed_columns, strict=False)
        if pd.notna(parsed) and pd.Timestamp(parsed) <= cutoff
    ]
    return data.loc[:, keep_columns] if keep_columns else pd.DataFrame(index=data.index)


def _statement_as_of_note(curr_date: str | None, freq: str) -> str:
    """Return a metadata note describing financial statement as-of filtering."""
    cutoff = _financial_statement_cutoff(curr_date, freq)
    if cutoff is None:
        return ""
    lag_days = (
        _QUARTERLY_REPORTING_LAG_DAYS
        if _normalize_freq(freq) == "quarterly"
        else _ANNUAL_REPORTING_LAG_DAYS
    )
    return (
        f"# As-of filter: curr_date={curr_date}, reporting_lag_days={lag_days}, "
        f"latest_period_end<={cutoff.strftime('%Y-%m-%d')}\n"
    )


def _get_financial_currency(ticker_obj: "yf.Ticker") -> str:
    """Best-effort fetch of the ticker's reported financial currency.

    Yahoo reports financials in the issuer's native currency (TWD for TWSE,
    JPY for Tokyo, EUR for XETRA, etc.). Without a currency tag, an LLM
    silently treats every number as USD.
    """
    try:
        return ticker_obj.info.get("financialCurrency") or "UNKNOWN"
    except Exception:
        logger.debug("Failed to fetch financial currency", exc_info=True)
        return "UNKNOWN"


def _humanize_number(value: object) -> str:
    """Render a numeric value in a human-readable scale (T / B / M).

    Plain integers and floats above 1M get a magnitude suffix; smaller
    values use comma separators. Non-numeric values are stringified.
    """
    if value is None:
        return "N/A"
    if not isinstance(value, (int, float)):
        return str(value)
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"{value / 1e12:.2f}T ({value:,.0f})"
    if abs_v >= 1e9:
        return f"{value / 1e9:.2f}B ({value:,.0f})"
    if abs_v >= 1e6:
        return f"{value / 1e6:.2f}M ({value:,.0f})"
    return f"{value:,.4f}" if isinstance(value, float) else f"{value:,}"


_CACHE_FRESH_HOURS = 12


def _read_cached_history(data_file: Path) -> pd.DataFrame:
    """Read a cached yfinance history CSV."""
    candidate_data = pd.read_csv(data_file)
    candidate_data["Date"] = pd.to_datetime(candidate_data["Date"])
    if candidate_data["Date"].dt.tz is not None:
        candidate_data["Date"] = candidate_data["Date"].dt.tz_localize(None)
    return candidate_data


def _download_history(candidate: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Download split- and dividend-adjusted OHLCV history for a symbol.

    Adjusted prices are required for technically meaningful indicators —
    raw close prices crash artificially across stock splits and reverse
    splits, which corrupts every moving average / Bollinger / MACD reading.
    """
    try:
        candidate_data = yf.download(
            candidate,
            start=start_date,
            end=end_date,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to download history for {candidate}") from exc
    return candidate_data.reset_index()


def _cache_covers_window(
    cached: pd.DataFrame, start_dt: datetime, last_required_dt: datetime
) -> bool:
    """Return whether ``cached`` spans ``[start_dt, last_required_dt]`` inclusively.

    The cache key no longer encodes the date range (P1-8), so any reuse
    must first verify the on-disk file actually covers the window the
    caller needs. ``last_required_dt`` is the latest *trading-day* the
    caller needs — NOT the exclusive ``end=`` value passed to yfinance.
    Comparing against the exclusive end would always fail (yfinance never
    returns a bar dated at ``end``), defeating the cache.

    A partial-coverage hit triggers a wider re-download rather than
    silently returning truncated history.
    """
    if cached.empty or "Date" not in cached.columns:
        return False
    cached_dates = pd.to_datetime(cached["Date"])
    if cached_dates.empty:
        return False
    return cached_dates.min() <= pd.Timestamp(start_dt) and cached_dates.max() >= pd.Timestamp(
        last_required_dt
    )


def _is_cache_fresh(data_file: Path, curr_date_dt: datetime) -> bool:
    """Return whether the on-disk cache should be reused for ``curr_date``.

    Historical (back-dated) runs always reuse the cache; today's run only
    reuses it if the file was written within ``_CACHE_FRESH_HOURS`` hours.
    Window coverage is checked separately by :func:`_cache_covers_window`,
    so a fresh-but-incomplete cache still triggers a re-download.
    """
    if not data_file.exists():
        return False
    if curr_date_dt.date() < datetime.now().date():
        return True
    age = datetime.now() - datetime.fromtimestamp(data_file.stat().st_mtime)
    return age < timedelta(hours=_CACHE_FRESH_HOURS)


def _load_history_candidate(  # noqa: PLR0913 -- mix of paths + dates + freshness is intentional
    candidate: str,
    data_file: Path,
    start_date: str,
    end_date: str,
    *,
    start_dt: datetime,
    last_required_dt: datetime,
    fresh: bool,
) -> pd.DataFrame:
    """Load cached history when safe, otherwise download and refresh cache.

    The cache filename is now ticker-only (P1-8) so adjacent run-dates
    reuse the same file. Each call verifies the cached window covers
    ``[start_dt, last_required_dt]`` inclusively; partial coverage falls
    back to a fresh download (using the exclusive ``end_date`` string
    yfinance expects) that overwrites the file with the wider window.
    """
    candidate_data = pd.DataFrame()
    if fresh:
        try:
            candidate_data = _read_cached_history(data_file)
        except Exception:
            logger.warning("Ignoring unreadable cache file %s", data_file, exc_info=True)
            candidate_data = pd.DataFrame()
        if not candidate_data.empty and not _cache_covers_window(
            candidate_data, start_dt, last_required_dt
        ):
            logger.info(
                "Cache for %s does not cover %s..%s; refreshing.", candidate, start_date, end_date
            )
            candidate_data = pd.DataFrame()

    if candidate_data.empty:
        candidate_data = _download_history(candidate, start_date, end_date)
        if not candidate_data.empty:
            candidate_data.to_csv(data_file, index=False)

    return candidate_data


def _resolve_history_with_cache(
    symbol: str, curr_date_dt: datetime
) -> tuple[str, pd.DataFrame, list[str]]:
    """Fetch (or load cached) 15-year OHLCV history for ``symbol``.

    The resulting DataFrame is shared between :func:`get_yfin_data_online`
    (which slices it by request window) and :func:`_get_stock_stats_bulk`
    (which feeds it through stockstats), so a single download per ticker
    services every market-analyst tool call.

    The cache filename is ticker-only (``<TICKER>-YFin-data.csv``); the
    requested ``[curr_date - 15y, curr_date + 1d]`` window is verified at
    read time so adjacent run dates reuse the same on-disk file. Without
    this, daily backtests would produce a new cache file per business day
    and never benefit from cache reuse.

    Args:
        symbol: User-supplied ticker symbol.
        curr_date_dt: The reference date used to build the 15-y window
            and decide whether the cache is still fresh.

    Returns:
        ``(resolved_symbol, dataframe, candidate_list)``.

    Raises:
        ValueError: If no market data is found across all candidates.
        RuntimeError: If every candidate raised on download.
    """
    config = get_config()

    # yfinance's `end=` is exclusive, so download with curr_date+1d to
    # actually include `curr_date` in the bar set. Coverage checks, in
    # contrast, must compare against the latest *trading-day* we need
    # back (curr_date itself), not the exclusive download end.
    download_end_dt = curr_date_dt + timedelta(days=1)
    last_required_dt = curr_date_dt
    start_dt = (pd.Timestamp(curr_date_dt) - pd.DateOffset(years=15)).to_pydatetime()
    start_date_str = pd.Timestamp(start_dt).strftime("%Y-%m-%d")
    end_date_str = pd.Timestamp(download_end_dt).strftime("%Y-%m-%d")

    cache_dir = Path(str(config.data_cache_dir))
    cache_dir.mkdir(parents=True, exist_ok=True)

    candidates = get_yfinance_symbol_candidates(symbol)
    data = pd.DataFrame()
    resolved_symbol = candidates[0]
    last_error: Exception | None = None
    fetched_any_candidate = False

    for candidate in candidates:
        data_file = cache_dir / f"{candidate}-YFin-data.csv"
        fresh = _is_cache_fresh(data_file, curr_date_dt)
        try:
            candidate_data = _load_history_candidate(
                candidate,
                data_file,
                start_date_str,
                end_date_str,
                start_dt=start_dt,
                last_required_dt=last_required_dt,
                fresh=fresh,
            )
        except Exception as exc:
            logger.debug("Failed to load market data for %s", candidate, exc_info=True)
            last_error = exc
            continue
        fetched_any_candidate = True
        if not candidate_data.empty:
            data = candidate_data
            resolved_symbol = candidate
            break

    if data.empty:
        tried = describe_symbol_candidates(symbol, candidates)
        if not fetched_any_candidate and last_error is not None:
            raise RuntimeError(
                f"Failed to fetch market data for symbol '{symbol}' (tried: {tried})"
            ) from last_error
        raise ValueError(f"No market data found for symbol '{symbol}' (tried: {tried}).")

    return resolved_symbol, data, candidates


def _has_meaningful_ticker_info(info: dict) -> bool:
    """Return whether yfinance info contains an actual resolved quote.

    Args:
        info (dict): The yfinance ticker info dictionary.

    Returns:
        bool: True if meaningful info is present, False otherwise.
    """
    identity_fields = ("longName", "shortName", "symbol", "quoteType", "market", "exchange")
    return any(info.get(field) for field in identity_fields)


def get_yfin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Fetch OHLCV stock data via yfinance (cached) and return as CSV string.

    Reads from the same 15-year on-disk cache used by the indicator
    pipeline so a single download services every market-analyst tool call.

    Args:
        symbol (str): Ticker symbol of the company.
        start_date (str): Start date in YYYY-MM-DD format.
        end_date (str): End date in YYYY-MM-DD format.

    Returns:
        str: CSV string containing stock data with header info.

    Raises:
        ValueError: If `start_date` or `end_date` does not match YYYY-MM-DD, or
            if the ticker symbol is empty.
    """
    start_dt, end_dt = _validate_date_range(start_date, end_date)

    try:
        resolved_symbol, data, candidates = _resolve_history_with_cache(symbol, end_dt)
    except (ValueError, RuntimeError) as exc:
        return f"[TOOL_ERROR] {exc}"

    data = data.copy()
    data["Date"] = pd.to_datetime(data["Date"])
    if data["Date"].dt.tz is not None:
        data["Date"] = data["Date"].dt.tz_localize(None)
    mask = (data["Date"] >= pd.Timestamp(start_dt)) & (data["Date"] <= pd.Timestamp(end_dt))
    sliced = data.loc[mask].copy()

    if sliced.empty:
        tried = describe_symbol_candidates(symbol, candidates)
        return (
            f"No data found for symbol '{symbol}' (tried: {tried}) "
            f"between {start_date} and {end_date}"
        )

    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in sliced.columns:
            sliced[col] = sliced[col].round(2)

    sliced["Date"] = sliced["Date"].dt.strftime("%Y-%m-%d")
    csv_string = sliced.to_csv(index=False)

    header = f"# Stock data for {resolved_symbol} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(sliced)}\n"
    header += "# Note: OHLC values are split- and dividend-adjusted (auto_adjust=True).\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


BEST_IND_PARAMS: dict[str, str] = {
    # Moving Averages
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: Reacts slowly; best for strategic trend confirmation rather than frequent entries."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets; pair with longer averages to filter false signals."
    ),
    # MACD Family
    "macd": (
        "MACD: Computes momentum via differences of EMAs. "
        "Usage: Look for crossovers and divergence as signals of trend changes. "
        "Tips: Confirm with other indicators in low-volatility or sideways markets."
    ),
    "macds": (
        "MACD Signal: An EMA smoothing of the MACD line. "
        "Usage: Use crossovers with the MACD line to trigger trades. "
        "Tips: Should be part of a broader strategy to avoid false positives."
    ),
    "macdh": (
        "MACD Histogram: Shows the gap between the MACD line and its signal. "
        "Usage: Visualise momentum strength and spot divergence early. "
        "Tips: Can be volatile; complement with additional filters in fast-moving markets."
    ),
    # Momentum / Oscillators
    "rsi": (
        "RSI: Measures momentum to flag overbought/oversold conditions. "
        "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
        "Tips: In strong trends RSI may remain extreme; always cross-check with trend analysis."
    ),
    "mfi": (
        "MFI: Money Flow Index, an RSI weighted by volume. "
        "Usage: >80 overbought, <20 oversold; divergence with price warns of reversal. "
        "Tips: More sensitive to volume spikes than RSI; pair with trend filter."
    ),
    "cci": (
        "CCI: Commodity Channel Index, default 20-period. "
        "Usage: > +100 overbought, < -100 oversold; divergence with price hints at reversal. "
        "Tips: Spikes in trending markets are normal; do not trade reversion blindly."
    ),
    "wr": (
        "Williams %R: Inverse fast stochastic, oscillates between 0 and -100. "
        "Usage: > -20 overbought, < -80 oversold; watch failure swings near extremes. "
        "Tips: Confirms with trend filter (e.g. ADX); signals are noisy in strong trends."
    ),
    "kdjk": (
        "Stochastic %K (KDJ K-line): fast stochastic momentum oscillator. "
        "Usage: > 80 overbought, < 20 oversold; %K crossing %D signals entries. "
        "Tips: Default 9-period; whipsaws in ranging markets, filter with ADX."
    ),
    "kdjd": (
        "Stochastic %D (KDJ D-line): smoothed %K. "
        "Usage: Confirms %K crossovers; %K above %D is bullish, below is bearish. "
        "Tips: Slower than %K but reduces false signals."
    ),
    # Trend Strength
    "adx": (
        "ADX: Average Directional Index, measures trend strength regardless of direction. "
        "Usage: ADX > 25 indicates a strong trend, < 20 a weak/ranging market. "
        "Tips: Pair with pdi (and the implicit -DI captured by dx) to confirm direction."
    ),
    "pdi": (
        "+DI: Positive Directional Indicator. "
        "Usage: When +DI is above -DI (reflected in rising dx) and ADX > 25, "
        "the trend is genuinely bullish; falling +DI warns of trend exhaustion. "
        "Tips: Pair with adx; meaningless on its own in low-ADX regimes."
    ),
    "stochrsi": (
        "Stochastic RSI: applies the stochastic oscillator to RSI itself. "
        "Usage: > 0.8 overbought, < 0.2 oversold; turns earlier than plain RSI. "
        "Tips: Very noisy on its own — confirm with trend (adx, sma) before trading reversals."
    ),
    "supertrend": (
        "Supertrend: ATR-banded trend follower; flips between long and short regimes. "
        "Usage: price above supertrend = bullish regime, below = bearish. "
        "Tips: Best as a regime filter; whipsaws inside Bollinger consolidations."
    ),
    "supertrend_ub": (
        "Supertrend upper band: the resistance side of the supertrend channel. "
        "Usage: A close that crosses above signals a regime flip to bullish. "
        "Tips: Pair with supertrend / supertrend_lb to read the full channel."
    ),
    "supertrend_lb": (
        "Supertrend lower band: the support side of the supertrend channel. "
        "Usage: A close that crosses below signals a regime flip to bearish. "
        "Tips: Pair with supertrend / supertrend_ub to read the full channel."
    ),
    # Volatility
    "boll": (
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
        "Usage: Acts as a dynamic benchmark for price movement. "
        "Tips: Combine with upper and lower bands to spot breakouts or reversals."
    ),
    "boll_ub": (
        "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
        "Usage: Signals potential overbought conditions and breakout zones. "
        "Tips: Confirm with other tools; prices may ride the band in strong trends."
    ),
    "boll_lb": (
        "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
        "Usage: Indicates potential oversold conditions. "
        "Tips: Use additional analysis to avoid false reversal signals."
    ),
    "atr": (
        "ATR: Average True Range, measures raw volatility. "
        "Usage: Set stop-loss levels and adjust position sizes based on current volatility. "
        "Tips: Reactive measure; use as part of a broader risk-management framework."
    ),
    # Volume / Trend
    "vwma": (
        "VWMA: A moving average weighted by volume. "
        "Usage: Confirm trends by integrating price action with volume data. "
        "Tips: Watch for skew from volume spikes; combine with other volume analyses."
    ),
    "obv": (
        "OBV: On-Balance Volume, cumulative volume that adds on up-days and subtracts on down-days. "
        "Usage: Confirms price-trend strength; divergence with price warns of weakening. "
        "Tips: Look at slope and divergence rather than the absolute value."
    ),
}


_MIN_BARS_FOR_RELIABLE_INDICATORS = 50


def _get_stock_stats_bulk_multi(
    symbol: str, indicators: list[str], curr_date: str
) -> tuple[str, dict[str, dict[str, str]], int]:
    """Resolve history once and compute every indicator in ``indicators``.

    Args:
        symbol: User-supplied ticker.
        indicators: List of stockstats indicator names; all assumed to be in
            :data:`BEST_IND_PARAMS`.
        curr_date: Current trading date in YYYY-MM-DD format.

    Returns:
        ``(resolved_symbol, {indicator: {YYYY-MM-DD: value_str}}, n_bars)``.
        ``n_bars`` is the number of OHLCV rows actually fed through
        stockstats so the formatter can warn when the history is shorter
        than the long-window indicators (sma_200 etc.) need.

    Raises:
        ValueError: If no market data is found.
        RuntimeError: If every history candidate raised on download.
    """
    curr_date_dt = _parse_yyyy_mm_dd(curr_date, "curr_date")
    resolved_symbol, data, _ = _resolve_history_with_cache(symbol, curr_date_dt)

    df = wrap(data.copy())
    df["Date"] = pd.to_datetime(df["Date"])
    if df["Date"].dt.tz is not None:
        df["Date"] = df["Date"].dt.tz_localize(None)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    result: dict[str, dict[str, str]] = {}
    for ind in indicators:
        df[ind]  # trigger stockstats to compute the column
        formatted = df[ind].apply(lambda v: "N/A" if pd.isna(v) else str(v))
        result[ind] = dict(zip(df["Date"], formatted, strict=False))
    return resolved_symbol, result, len(df)


def _validate_indicators(indicators: list[str]) -> None:
    """Ensure every requested indicator is supported."""
    if not indicators:
        raise ValueError("indicators must contain at least one indicator.")
    unsupported = [ind for ind in indicators if ind not in BEST_IND_PARAMS]
    if unsupported:
        raise ValueError(
            f"Indicator(s) {unsupported} not supported. Please choose from: "
            f"{sorted(BEST_IND_PARAMS.keys())}"
        )


def get_stock_stats_indicators_batch(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicators: Annotated[list[str], "list of technical indicators"],
    curr_date: Annotated[str, "current trading date in YYYY-MM-DD format"],
    look_back_days: Annotated[int, "look-back window in days"] = 30,
) -> str:
    """Compute every requested indicator against a single wrapped history.

    A single call to :func:`_get_stock_stats_bulk_multi` services all
    indicators, so the 15-y CSV is wrapped exactly once even when the
    Market Analyst asks for the maximum eight indicators at once.

    Output is chronological (oldest -> newest) and only emits actual
    trading days, so weekend / holiday placeholder rows no longer waste
    LLM context.
    """
    _validate_indicators(indicators)
    if look_back_days < 0:
        raise ValueError("look_back_days must be >= 0.")

    curr_date_dt = _parse_yyyy_mm_dd(curr_date, "curr_date")
    before = curr_date_dt - relativedelta(days=look_back_days)
    before_str = before.strftime("%Y-%m-%d")
    end_str = curr_date_dt.strftime("%Y-%m-%d")

    _, data_map, n_bars = _get_stock_stats_bulk_multi(symbol, indicators, curr_date)

    preamble = ""
    if n_bars < _MIN_BARS_FOR_RELIABLE_INDICATORS:
        preamble = (
            f"# DATA WARNING: only {n_bars} OHLCV bars are available for "
            f"{symbol} up to {end_str}; indicators that need >= "
            f"{_MIN_BARS_FOR_RELIABLE_INDICATORS} bars (sma_50, sma_200, supertrend, "
            f"long ADX, etc.) will return mostly N/A. Treat the values below as "
            f"unreliable for trend / regime decisions; rely on price action and "
            f"shorter-window indicators (10 EMA, rsi) instead.\n\n"
        )

    sections: list[str] = []
    for ind in indicators:
        ind_data = data_map[ind]
        sorted_dates = sorted(d for d in ind_data if before_str <= d <= end_str)
        if sorted_dates:
            ind_string = "".join(f"{d}: {ind_data[d]}\n" for d in sorted_dates)
        else:
            ind_string = "(no trading days in window)\n"
        sections.append(
            f"## {ind} values from {before_str} to {end_str} (chronological, trading days only):\n\n"
            + ind_string
            + "\n\n"
            + BEST_IND_PARAMS[ind]
        )
    return preamble + "\n\n".join(sections)


def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Single-indicator wrapper around :func:`get_stock_stats_indicators_batch`.

    Args:
        symbol: Ticker symbol of the company.
        indicator: Technical indicator to calculate.
        curr_date: Current trading date in YYYY-MM-DD format.
        look_back_days: Number of days to look back.

    Returns:
        Formatted string containing indicator values and a description.

    Raises:
        ValueError: If the requested indicator is not supported, ``curr_date``
            does not match YYYY-MM-DD, the symbol is empty, or no market data
            is available.
    """
    return get_stock_stats_indicators_batch(symbol, [indicator], curr_date, look_back_days)


def _resolve_ticker_info(ticker: str) -> tuple[str, dict[str, object], list[str]]:
    """Iterate ticker candidates and return the first with meaningful info.

    Returns ``(resolved_ticker, info_dict, candidates)`` where ``info_dict``
    is empty if every candidate failed.

    Raises:
        RuntimeError: If every candidate raised on download.
    """
    candidates = get_yfinance_symbol_candidates(ticker)
    last_error: Exception | None = None
    fetched_any_candidate = False
    for candidate in candidates:
        try:
            candidate_info = yf.Ticker(candidate).info
        except Exception as exc:
            logger.debug("Failed to fetch fundamentals for %s", candidate, exc_info=True)
            last_error = exc
            continue
        fetched_any_candidate = True
        if _has_meaningful_ticker_info(candidate_info):
            return candidate, candidate_info, candidates

    if not fetched_any_candidate and last_error is not None:
        tried = describe_symbol_candidates(ticker, candidates)
        raise RuntimeError(
            f"Failed to fetch fundamentals for symbol '{ticker}' (tried: {tried})"
        ) from last_error
    return candidates[0], {}, candidates


_DILUTED_EPS_ROW_KEYS: tuple[str, ...] = ("Diluted EPS", "DilutedEPS", "Basic EPS", "BasicEPS")
_BOOK_EQUITY_ROW_KEYS: tuple[str, ...] = (
    "Common Stock Equity",
    "Stockholders Equity",
    "Total Equity Gross Minority Interest",
)
_SHARES_ROW_KEYS: tuple[str, ...] = (
    "Ordinary Shares Number",
    "Share Issued",
    "Common Stock Shares Outstanding",
)


def _last_n_quarter_sum(
    statement: pd.DataFrame, row_keys: tuple[str, ...], n: int
) -> float | None:
    """Return the sum of the latest ``n`` quarterly columns for the first matching row.

    Statement columns are filtered point-in-time, sorted left-to-right by
    period end date by yfinance. Picking the last ``n`` columns gives the
    TTM-most approximation that respects the as-of cutoff.
    """
    if statement.empty:
        return None
    for key in row_keys:
        if key in statement.index:
            row = statement.loc[key].dropna()
            if row.empty:
                continue
            try:
                values = row.astype(float).tolist()
            except (TypeError, ValueError):
                continue
            if not values:
                continue
            sample = values[-n:] if len(values) >= n else values
            return float(sum(sample))
    return None


def _latest_row_value(statement: pd.DataFrame, row_keys: tuple[str, ...]) -> float | None:
    """Return the most recent (rightmost) non-NaN value for the first matching row key."""
    if statement.empty:
        return None
    for key in row_keys:
        if key in statement.index:
            row = statement.loc[key].dropna()
            if row.empty:
                continue
            try:
                return float(row.astype(float).iloc[-1])
            except (TypeError, ValueError):
                continue
    return None


def _close_on_or_before(symbol: str, curr_date_dt: datetime) -> float | None:
    """Return the latest cached close price at or before ``curr_date_dt``."""
    try:
        _, data, _ = _resolve_history_with_cache(symbol, curr_date_dt)
    except Exception:
        logger.debug("Failed to resolve history for historical valuation", exc_info=True)
        return None
    if data.empty or "Date" not in data.columns:
        return None
    dates = pd.to_datetime(data["Date"])
    mask = dates <= pd.Timestamp(curr_date_dt)
    eligible = data.loc[mask]
    if eligible.empty or "Close" not in eligible.columns:
        return None
    try:
        return float(eligible["Close"].iloc[-1])
    except (TypeError, ValueError):
        return None


def _historical_valuation_block(
    resolved_ticker: str, ticker_obj: "yf.Ticker", curr_date: str
) -> list[str]:
    """Compute P/E and P/B from cached close + filtered statements.

    yfinance.info is current-only, so for back-dated runs this block is
    the only way to surface valuation multiples. Returns one line per
    computable metric; silently skips any metric whose inputs are
    missing rather than emitting "N/A" placeholders that would mislead
    the LLM.
    """
    curr_dt = _parse_yyyy_mm_dd(curr_date, "curr_date")
    close = _close_on_or_before(resolved_ticker, curr_dt)
    if close is None or close <= 0:
        return []

    try:
        income = _filter_statement_as_of(ticker_obj.quarterly_income_stmt, curr_date, "quarterly")
    except Exception:
        logger.debug("Failed to load income statement for historical valuation", exc_info=True)
        income = pd.DataFrame()
    try:
        balance = _filter_statement_as_of(
            ticker_obj.quarterly_balance_sheet, curr_date, "quarterly"
        )
    except Exception:
        logger.debug("Failed to load balance sheet for historical valuation", exc_info=True)
        balance = pd.DataFrame()

    ttm_eps = _last_n_quarter_sum(income, _DILUTED_EPS_ROW_KEYS, 4)
    book_equity = _latest_row_value(balance, _BOOK_EQUITY_ROW_KEYS)
    shares = _latest_row_value(balance, _SHARES_ROW_KEYS)
    bvps = book_equity / shares if book_equity and shares and shares > 0 else None

    lines: list[str] = []
    lines.append(f"Close (last <= {curr_date}): {close:.4f}")
    if ttm_eps is not None and ttm_eps > 0:
        lines.append(f"TTM Diluted EPS (sum of last 4 quarters): {ttm_eps:.4f}")
        lines.append(f"Historical P/E: {close / ttm_eps:.2f}")
    if bvps is not None and bvps > 0:
        lines.append(f"Book Value per Share: {bvps:.4f}")
        lines.append(f"Historical P/B: {close / bvps:.2f}")
    return lines


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Get company fundamentals overview from yfinance.

    For current-date runs the standard ``yfinance.info`` snapshot is
    returned. For back-dated ``curr_date`` (point-in-time analysis)
    ``yfinance.info`` is current-only and would leak future data, so the
    function falls back to a computed-locally block: close price at or
    before ``curr_date`` from the 15-y OHLCV cache, TTM diluted EPS from
    the as-of-filtered income statement, and book value per share from
    the as-of-filtered balance sheet — giving Historical P/E and P/B
    multiples without lookahead bias.

    Args:
        ticker (str): Ticker symbol of the company.
        curr_date (str | None, optional): Current date used as a point-in-time
            boundary. Defaults to None.

    Returns:
        str: Formatted string containing fundamentals overview.
    """
    _as_of_datetime(curr_date)

    resolved_ticker, info, candidates = _resolve_ticker_info(ticker)

    if not info:
        tried = describe_symbol_candidates(ticker, candidates)
        return f"No fundamentals data found for symbol '{ticker}' (tried: {tried})"

    profile_fields = [
        ("Name", info.get("longName")),
        ("Sector", info.get("sector")),
        ("Industry", info.get("industry")),
    ]
    big_number_fields = {
        "Market Cap",
        "Revenue (TTM)",
        "Gross Profit",
        "EBITDA",
        "Net Income",
        "Free Cash Flow",
    }
    snapshot_fields = [
        ("Name", info.get("longName")),
        ("Sector", info.get("sector")),
        ("Industry", info.get("industry")),
        ("Market Cap", info.get("marketCap")),
        ("PE Ratio (TTM)", info.get("trailingPE")),
        ("Forward PE", info.get("forwardPE")),
        ("PEG Ratio", info.get("pegRatio")),
        ("Price to Book", info.get("priceToBook")),
        ("EPS (TTM)", info.get("trailingEps")),
        ("Forward EPS", info.get("forwardEps")),
        ("Dividend Yield", info.get("dividendYield")),
        ("Beta", info.get("beta")),
        ("52 Week High", info.get("fiftyTwoWeekHigh")),
        ("52 Week Low", info.get("fiftyTwoWeekLow")),
        ("50 Day Average", info.get("fiftyDayAverage")),
        ("200 Day Average", info.get("twoHundredDayAverage")),
        ("Revenue (TTM)", info.get("totalRevenue")),
        ("Gross Profit", info.get("grossProfits")),
        ("EBITDA", info.get("ebitda")),
        ("Net Income", info.get("netIncomeToCommon")),
        ("Profit Margin", info.get("profitMargins")),
        ("Operating Margin", info.get("operatingMargins")),
        ("Return on Equity", info.get("returnOnEquity")),
        ("Return on Assets", info.get("returnOnAssets")),
        ("Debt to Equity", info.get("debtToEquity")),
        ("Current Ratio", info.get("currentRatio")),
        ("Book Value", info.get("bookValue")),
        ("Free Cash Flow", info.get("freeCashflow")),
    ]

    is_historical = _is_historical_date(curr_date)
    fields = profile_fields if is_historical else snapshot_fields
    lines = []
    for label, value in fields:
        if value is None:
            continue
        if label in big_number_fields:
            lines.append(f"{label}: {_humanize_number(value)}")
        else:
            lines.append(f"{label}: {value}")

    if is_historical and curr_date is not None:
        try:
            valuation_lines = _historical_valuation_block(
                resolved_ticker, yf.Ticker(resolved_ticker), curr_date
            )
        except Exception:
            logger.debug("Historical valuation block failed", exc_info=True)
            valuation_lines = []
        if valuation_lines:
            lines.append("")
            lines.append("# Computed locally from cached close + as-of-filtered statements:")
            lines.extend(valuation_lines)

    header = f"# Company Fundamentals for {resolved_ticker}\n"
    if curr_date is not None:
        header += f"# Current trading date: {curr_date}\n"
    header += f"# Reporting currency (info.financialCurrency): {info.get('financialCurrency') or 'UNKNOWN'}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    if is_historical:
        header += (
            "# Snapshot valuation/market metrics from yfinance.info are omitted "
            "for historical dates (info is current-only); P/E and P/B are "
            "instead computed locally from cached OHLCV + as-of-filtered "
            "statements (see 'Computed locally' block below).\n"
            "# For full historical revenue, EPS, and balance-sheet detail call "
            "get_income_statement / get_balance_sheet / get_cashflow with "
            "curr_date set -- those endpoints are also point-in-time-filtered.\n"
        )
    header += "\n"

    return header + "\n".join(lines)


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Get balance sheet data from yfinance.

    Args:
        ticker (str): Ticker symbol of the company.
        freq (str, optional): Frequency of data ('annual' or 'quarterly'). Defaults to "quarterly".
        curr_date (str | None, optional): Current date used as a point-in-time boundary. Defaults to None.

    Returns:
        str: CSV string containing balance sheet data.
    """
    freq = _normalize_freq(freq)
    _as_of_datetime(curr_date)
    candidates = get_yfinance_symbol_candidates(ticker)
    data = pd.DataFrame()
    resolved_ticker = candidates[0]
    currency = "UNKNOWN"
    last_error: Exception | None = None
    fetched_any_candidate = False

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            candidate_data = (
                ticker_obj.quarterly_balance_sheet
                if freq == "quarterly"
                else ticker_obj.balance_sheet
            )
        except Exception as exc:
            logger.debug("Failed to fetch balance sheet for %s", candidate, exc_info=True)
            last_error = exc
            continue
        fetched_any_candidate = True
        if candidate_data is None or candidate_data.empty:
            continue
        candidate_data = _filter_statement_as_of(candidate_data, curr_date, freq)
        if not candidate_data.empty:
            data = candidate_data
            resolved_ticker = candidate
            currency = _get_financial_currency(ticker_obj)
            break

    if data.empty:
        tried = describe_symbol_candidates(ticker, candidates)
        if not fetched_any_candidate and last_error is not None:
            raise RuntimeError(
                f"Failed to fetch balance sheet for symbol '{ticker}' (tried: {tried})"
            ) from last_error
        return (
            f"No balance sheet data found for symbol '{ticker}' (tried: {tried}) "
            f"as of {curr_date or 'latest'}"
        )

    csv_string = data.to_csv()

    header = f"# Balance Sheet data for {resolved_ticker} ({freq})\n"
    header += f"# Reported currency: {currency}\n"
    header += _statement_as_of_note(curr_date, freq)
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cash flow data from yfinance.

    Args:
        ticker (str): Ticker symbol of the company.
        freq (str, optional): Frequency of data ('annual' or 'quarterly'). Defaults to "quarterly".
        curr_date (str | None, optional): Current date used as a point-in-time boundary. Defaults to None.

    Returns:
        str: CSV string containing cash flow data.
    """
    freq = _normalize_freq(freq)
    _as_of_datetime(curr_date)
    candidates = get_yfinance_symbol_candidates(ticker)
    data = pd.DataFrame()
    resolved_ticker = candidates[0]
    currency = "UNKNOWN"
    last_error: Exception | None = None
    fetched_any_candidate = False

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            candidate_data = (
                ticker_obj.quarterly_cashflow if freq == "quarterly" else ticker_obj.cashflow
            )
        except Exception as exc:
            logger.debug("Failed to fetch cash flow for %s", candidate, exc_info=True)
            last_error = exc
            continue
        fetched_any_candidate = True
        if candidate_data is None or candidate_data.empty:
            continue
        candidate_data = _filter_statement_as_of(candidate_data, curr_date, freq)
        if not candidate_data.empty:
            data = candidate_data
            resolved_ticker = candidate
            currency = _get_financial_currency(ticker_obj)
            break

    if data.empty:
        tried = describe_symbol_candidates(ticker, candidates)
        if not fetched_any_candidate and last_error is not None:
            raise RuntimeError(
                f"Failed to fetch cash flow for symbol '{ticker}' (tried: {tried})"
            ) from last_error
        return (
            f"No cash flow data found for symbol '{ticker}' (tried: {tried}) "
            f"as of {curr_date or 'latest'}"
        )

    csv_string = data.to_csv()

    header = f"# Cash Flow data for {resolved_ticker} ({freq})\n"
    header += f"# Reported currency: {currency}\n"
    header += _statement_as_of_note(curr_date, freq)
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement data from yfinance.

    Args:
        ticker (str): Ticker symbol of the company.
        freq (str, optional): Frequency of data ('annual' or 'quarterly'). Defaults to "quarterly".
        curr_date (str | None, optional): Current date used as a point-in-time boundary. Defaults to None.

    Returns:
        str: CSV string containing income statement data.
    """
    freq = _normalize_freq(freq)
    _as_of_datetime(curr_date)
    candidates = get_yfinance_symbol_candidates(ticker)
    data = pd.DataFrame()
    resolved_ticker = candidates[0]
    currency = "UNKNOWN"
    last_error: Exception | None = None
    fetched_any_candidate = False

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            candidate_data = (
                ticker_obj.quarterly_income_stmt if freq == "quarterly" else ticker_obj.income_stmt
            )
        except Exception as exc:
            logger.debug("Failed to fetch income statement for %s", candidate, exc_info=True)
            last_error = exc
            continue
        fetched_any_candidate = True
        if candidate_data is None or candidate_data.empty:
            continue
        candidate_data = _filter_statement_as_of(candidate_data, curr_date, freq)
        if not candidate_data.empty:
            data = candidate_data
            resolved_ticker = candidate
            currency = _get_financial_currency(ticker_obj)
            break

    if data.empty:
        tried = describe_symbol_candidates(ticker, candidates)
        if not fetched_any_candidate and last_error is not None:
            raise RuntimeError(
                f"Failed to fetch income statement for symbol '{ticker}' (tried: {tried})"
            ) from last_error
        return (
            f"No income statement data found for symbol '{ticker}' (tried: {tried}) "
            f"as of {curr_date or 'latest'}"
        )

    csv_string = data.to_csv()

    header = f"# Income Statement data for {resolved_ticker} ({freq})\n"
    header += f"# Reported currency: {currency}\n"
    header += _statement_as_of_note(curr_date, freq)
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def _resolved_ticker_obj(ticker: str) -> tuple[str, "yf.Ticker", list[str]]:
    """Return the first yf.Ticker candidate whose ``.info`` carries identity fields.

    Reuses :func:`_resolve_ticker_info` so every new yfinance-backed
    tool (analyst ratings, earnings calendar, holders, short interest,
    dividends/splits) gets the same fuzzy-resolution semantics as
    :func:`get_fundamentals`.
    """
    resolved_ticker, _info, candidates = _resolve_ticker_info(ticker)
    return resolved_ticker, yf.Ticker(resolved_ticker), candidates


def _as_of_filter_dated_frame(
    df: pd.DataFrame, curr_date: str | None, date_column: str
) -> pd.DataFrame:
    """Return rows whose ``date_column`` is on or before ``curr_date``.

    Falls back to the input frame untouched when ``curr_date`` is None or
    the column is missing / unparsable, so callers can safely chain
    this past best-effort yfinance shapes.
    """
    as_of = _as_of_datetime(curr_date)
    if as_of is None or df is None or df.empty or date_column not in df.columns:
        return df
    try:
        dates = pd.to_datetime(df[date_column], errors="coerce", utc=True).dt.tz_localize(None)
    except Exception:
        return df
    return df.loc[dates <= pd.Timestamp(as_of)]


def get_analyst_ratings(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Retrieve analyst rating history for ``ticker``.

    yfinance exposes a quarterly rollup of strong-buy / buy / hold /
    sell / strong-sell counts (``recommendations``) plus a snapshot
    summary (``recommendations_summary``); both are surfaced when
    ``curr_date`` is None or in the present. For historical
    ``curr_date`` the snapshot is suppressed (current-only) but the
    rolling history is filtered to keep only periods on or before
    ``curr_date`` to avoid lookahead.
    """
    resolved_ticker, ticker_obj, candidates = _resolved_ticker_obj(ticker)

    try:
        recs = ticker_obj.recommendations
    except Exception as exc:
        logger.debug("Failed to fetch analyst recommendations", exc_info=True)
        return f"[TOOL_ERROR] Analyst ratings unavailable for {ticker}: {exc!s}"

    if recs is None or recs.empty:
        tried = describe_symbol_candidates(ticker, candidates)
        return f"[NO_DATA] No analyst ratings for {ticker} (tried: {tried})"

    recs = recs.copy()
    # Some yfinance variants index by date instead of carrying a column.
    if isinstance(recs.index, pd.DatetimeIndex) and "period" not in recs.columns:
        recs = recs.reset_index().rename(columns={"index": "period"})
    if "period" in recs.columns:
        recs = _as_of_filter_dated_frame(recs, curr_date, "period")

    header = f"# Analyst Ratings (rolling counts) for {resolved_ticker}\n"
    if curr_date is not None:
        header += f"# Current trading date: {curr_date}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    body = (
        recs.to_csv(index=False)
        if not recs.empty
        else "(no historical periods on/before curr_date)\n"
    )

    # Recommendations summary is current-only; emit only for present-day runs.
    if not _is_historical_date(curr_date):
        try:
            summary = ticker_obj.recommendations_summary
            if summary is not None and not summary.empty:
                body += "\n\n# recommendations_summary (current snapshot, NOT point-in-time):\n"
                body += summary.to_csv(index=False)
        except Exception:
            logger.debug("recommendations_summary fetch failed", exc_info=True)

    return header + body


def get_earnings_calendar(  # noqa: C901, PLR0912, PLR0915 -- yfinance returns multiple variants
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Retrieve upcoming + recent earnings dates and the calendar summary.

    Combines ``yf.Ticker.calendar`` (a snapshot of the next confirmed
    event) with ``yf.Ticker.earnings_dates`` (a rolling history /
    forecast). For historical ``curr_date`` the rolling table is split
    into past (<= curr_date) and forward (> curr_date) sections so the
    News analyst can reason about catalyst proximity without leaking
    the actual reported figure from a future filing.
    """
    resolved_ticker, ticker_obj, _candidates = _resolved_ticker_obj(ticker)

    pieces: list[str] = [f"# Earnings calendar for {resolved_ticker}"]
    if curr_date is not None:
        pieces.append(f"# Current trading date: {curr_date}")
    pieces.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Calendar snapshot. yfinance returns either a dict (newer releases) or a
    # pandas DataFrame (older releases); a bare `if cal:` check raises
    # `ValueError: The truth value of a DataFrame is ambiguous` on the
    # DataFrame branch, so we dispatch on type explicitly instead.
    try:
        cal = ticker_obj.calendar
    except Exception:
        cal = None
    if isinstance(cal, dict) and cal:
        pieces.append("\n## Calendar snapshot (yfinance.calendar)")
        for key, value in cal.items():
            pieces.append(f"- {key}: {value}")
    elif isinstance(cal, pd.DataFrame) and not cal.empty:
        pieces.append("\n## Calendar snapshot (yfinance.calendar)")
        try:
            pieces.append(cal.to_csv())
        except Exception:
            pieces.append(str(cal))

    # Earnings dates table — split past vs forward when curr_date is set.
    try:
        ed = ticker_obj.earnings_dates
    except Exception:
        ed = None
    if ed is not None and not ed.empty:
        ed = ed.copy()
        if isinstance(ed.index, pd.DatetimeIndex):
            ed_dates = ed.index.tz_localize(None) if ed.index.tz is not None else ed.index
            ed = ed.reset_index()
            ed.iloc[:, 0] = ed_dates
        cutoff = _as_of_datetime(curr_date)
        if cutoff is not None and len(ed.columns) >= 1:
            first_col = ed.columns[0]
            try:
                parsed = pd.to_datetime(ed[first_col], errors="coerce", utc=True).dt.tz_localize(
                    None
                )
            except Exception:
                parsed = pd.to_datetime(ed[first_col], errors="coerce")
            past = ed.loc[parsed <= pd.Timestamp(cutoff)]
            future = ed.loc[parsed > pd.Timestamp(cutoff)]
            if not past.empty:
                pieces.append("\n## Past earnings dates (on/before curr_date)")
                pieces.append(past.to_csv(index=False))
            if not future.empty:
                pieces.append(
                    "\n## Forward earnings dates (after curr_date, surprise columns redacted to avoid lookahead)"
                )
                surprise_cols = [
                    c for c in future.columns if "Surprise" in str(c) or "Reported" in str(c)
                ]
                future_redacted = future.copy()
                for col in surprise_cols:
                    future_redacted[col] = "[REDACTED]"
                pieces.append(future_redacted.to_csv(index=False))
        else:
            pieces.append("\n## Earnings dates")
            pieces.append(ed.to_csv(index=False))

    if len(pieces) <= 3:
        return f"[NO_DATA] No earnings calendar / dates available for {ticker}"
    return "\n".join(pieces)


def get_institutional_holders(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Retrieve institutional + major holders snapshots.

    yfinance only exposes the *current* holders snapshot; there is no
    historical archive, so for back-dated ``curr_date`` the function
    returns a clearly-flagged ``[NO_DATA]`` note instead of leaking
    present-day positioning into a back-test.
    """
    if _is_historical_date(curr_date):
        return (
            f"[NO_DATA] Institutional holders for {ticker}: yfinance exposes the "
            "current snapshot only; historical positioning is not available. "
            "Returning no rows to avoid lookahead bias."
        )

    resolved_ticker, ticker_obj, _candidates = _resolved_ticker_obj(ticker)

    pieces: list[str] = [f"# Institutional holders for {resolved_ticker} (current snapshot)"]
    if curr_date is not None:
        pieces.append(f"# Current trading date: {curr_date}")
    pieces.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    has_data = False
    try:
        major = ticker_obj.major_holders
        if major is not None and not major.empty:
            pieces.append("\n## major_holders")
            pieces.append(major.to_csv(index=False))
            has_data = True
    except Exception:
        logger.debug("major_holders fetch failed", exc_info=True)
    try:
        inst = ticker_obj.institutional_holders
        if inst is not None and not inst.empty:
            pieces.append("\n## institutional_holders")
            pieces.append(inst.to_csv(index=False))
            has_data = True
    except Exception:
        logger.debug("institutional_holders fetch failed", exc_info=True)

    if not has_data:
        return f"[NO_DATA] No institutional / major holders rows for {ticker}"
    return "\n".join(pieces)


def get_short_interest(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Retrieve short interest, days-to-cover, and float-percentage metrics.

    Sourced from ``yfinance.info`` which is current-only; for
    back-dated ``curr_date`` the function returns a ``[NO_DATA]`` note
    to keep historical decisions free of forward-looking positioning.
    """
    if _is_historical_date(curr_date):
        return (
            f"[NO_DATA] Short interest for {ticker}: yfinance.info is current-only. "
            "Returning no rows to avoid lookahead bias on historical runs."
        )

    resolved_ticker, ticker_obj, _candidates = _resolved_ticker_obj(ticker)

    try:
        info = ticker_obj.info or {}
    except Exception as exc:
        return f"[TOOL_ERROR] Short interest unavailable for {ticker}: {exc!s}"

    fields = [
        ("Shares Short", info.get("sharesShort")),
        ("Shares Short (prior month)", info.get("sharesShortPriorMonth")),
        ("Short Ratio (days to cover)", info.get("shortRatio")),
        ("Short Percent of Float", info.get("shortPercentOfFloat")),
        ("Float Shares", info.get("floatShares")),
        ("Shares Outstanding", info.get("sharesOutstanding")),
    ]
    populated = [(label, value) for label, value in fields if value is not None]
    if not populated:
        return f"[NO_DATA] yfinance.info did not surface any short-interest fields for {ticker}"

    header = f"# Short interest for {resolved_ticker} (current snapshot)\n"
    if curr_date is not None:
        header += f"# Current trading date: {curr_date}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + "\n".join(f"{label}: {value}" for label, value in populated)


def get_dividends_splits(
    ticker: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "end date in YYYY-MM-DD format"],
) -> str:
    """Retrieve dividends and stock-split events within ``[start_date, end_date]``.

    Both ``yf.Ticker.dividends`` and ``.splits`` are date-indexed
    historical Series, so this tool is point-in-time correct without
    further filtering: pass ``end_date == curr_date`` to back-test
    cleanly.
    """
    start_dt, end_dt = _validate_date_range(start_date, end_date)
    resolved_ticker, ticker_obj, _candidates = _resolved_ticker_obj(ticker)

    pieces: list[str] = [
        f"# Dividends and splits for {resolved_ticker} from {start_date} to {end_date}",
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    found_any = False

    for label, attr in (("dividends", "dividends"), ("splits", "splits")):
        try:
            series = getattr(ticker_obj, attr)
        except Exception:
            logger.debug("%s fetch failed", attr, exc_info=True)
            continue
        if series is None or series.empty:
            continue
        s = series.copy()
        idx = s.index
        if isinstance(idx, pd.DatetimeIndex) and idx.tz is not None:
            s.index = idx.tz_localize(None)
        filtered = s.loc[(s.index >= pd.Timestamp(start_dt)) & (s.index <= pd.Timestamp(end_dt))]
        if filtered.empty:
            continue
        found_any = True
        pieces.append(f"\n## {label}")
        pieces.append(filtered.to_csv(header=[label]))

    if not found_any:
        return f"[NO_DATA] No dividends or splits for {ticker} between {start_date} and {end_date}"
    return "\n".join(pieces)


_INSIDER_HISTORY_HORIZON_DAYS = 180
_NO_DATA_PREFIX = "[NO_DATA]"


def _insider_history_unavailable_message(ticker: str, curr_date: str | None) -> str | None:
    """Return a no-data message if curr_date is older than yfinance's horizon.

    The message is prefixed with ``[NO_DATA]`` to match the sentinel used by
    the news / RSS fallback path in :mod:`tradingagents.dataflows.news`, so
    LLM prompts can deterministically distinguish "no data available" from
    a real partial result.
    """
    as_of = _as_of_datetime(curr_date)
    if as_of is None:
        return None
    horizon = datetime.now().date() - timedelta(days=_INSIDER_HISTORY_HORIZON_DAYS)
    if as_of.date() >= horizon:
        return None
    return (
        f"{_NO_DATA_PREFIX} Insider Transactions for {ticker} unavailable.\n"
        f"# Requested as_of: {curr_date}\n"
        f"# yfinance exposes only the most recent ~{_INSIDER_HISTORY_HORIZON_DAYS} days "
        f"of insider transactions; historical data before "
        f"{horizon.strftime('%Y-%m-%d')} is not available through this tool. "
        f"Returning no rows to avoid lookahead bias.\n"
    )


def _filter_insider_by_date(candidate_data: pd.DataFrame, as_of: datetime | None) -> pd.DataFrame:
    """Restrict insider rows to those on or before as_of, when possible."""
    if as_of is None:
        return candidate_data
    date_columns = [column for column in candidate_data.columns if "date" in str(column).lower()]
    if not date_columns:
        return candidate_data
    dates = pd.to_datetime(candidate_data[date_columns[0]], errors="coerce")
    return candidate_data.loc[dates <= pd.Timestamp(as_of)]


_INDEX_BY_REGION: dict[str, tuple[str, str]] = {
    "US": ("^GSPC", "S&P 500"),
    "TW": ("^TWII", "TAIEX"),
    "HK": ("^HSI", "Hang Seng"),
    "JP": ("^N225", "Nikkei 225"),
    "CN": ("000001.SS", "Shanghai Composite"),
    "DE": ("^GDAXI", "DAX"),
    "KR": ("^KS11", "KOSPI"),
    "GB": ("^FTSE", "FTSE 100"),
    "FR": ("^FCHI", "CAC 40"),
    "NL": ("^AEX", "AEX"),
    "AU": ("^AXJO", "S&P/ASX 200"),
    "CA": ("^GSPTSE", "S&P/TSX Composite"),
}
_GLOBAL_PROBES: tuple[tuple[str, str], ...] = (
    ("^TNX", "US 10-year Treasury yield"),
    ("^VIX", "CBOE Volatility Index (VIX)"),
)


def _probe_market_index(symbol: str, label: str, start_dt: datetime, end_dt: datetime) -> str:
    """Render a one-paragraph snapshot of an index over ``[start_dt, end_dt]``."""
    try:
        hist = yf.Ticker(symbol).history(
            start=start_dt, end=end_dt + timedelta(days=1), auto_adjust=False
        )
    except Exception as exc:
        logger.debug("Failed to fetch %s history", symbol, exc_info=True)
        return f"## {label} ({symbol})\n[TOOL_ERROR] {exc!s}"
    if hist is None or hist.empty:
        return f"## {label} ({symbol})\n[NO_DATA] No history returned for the requested window."

    closes = hist["Close"].dropna()
    if closes.empty:
        return f"## {label} ({symbol})\n[NO_DATA] All close values were NaN for the window."

    last_close = float(closes.iloc[-1])
    first_close = float(closes.iloc[0])
    pct = (last_close / first_close - 1.0) * 100.0 if first_close else 0.0
    high = float(closes.max())
    low = float(closes.min())
    return (
        f"## {label} ({symbol})\n"
        f"Latest close: {last_close:.2f}\n"
        f"Window change: {pct:+.2f}%\n"
        f"Window range: low {low:.2f} -- high {high:.2f}"
    )


def get_market_context(
    ticker: Annotated[str, "ticker symbol; used to resolve the local index region"],
    curr_date: Annotated[str, "current trading date in YYYY-MM-DD format"],
    look_back_days: Annotated[int, "look-back window in days"] = 5,
) -> str:
    """Return a compact regional macro snapshot for the News Analyst.

    Surfaces: the local exchange index (derived from ``ticker``'s suffix
    via :func:`tradingagents.dataflows.tickers.get_news_locale`), the US
    10-year Treasury yield (``^TNX``), and the CBOE VIX. This gives
    Taiwan / HK / JP / DE analysts the regional context they need instead
    of forcing them to infer it from headlines.

    Args:
        ticker: User-supplied ticker. Suffix decides the local index
            (e.g. ``.TW`` -> ``^TWII``, ``.DE`` -> ``^GDAXI``); falls
            back to ``^GSPC`` for US / unsuffixed tickers.
        curr_date: As-of date in YYYY-MM-DD format.
        look_back_days: Window for the change / high-low summary.

    Returns:
        Formatted multi-section string with index, 10y yield, and VIX
        snapshots. Each section reports ``[NO_DATA]`` or
        ``[TOOL_ERROR]`` independently so a single failed probe does not
        nullify the entire context.
    """
    curr_dt = _parse_yyyy_mm_dd(curr_date, "curr_date")
    if look_back_days < 1:
        raise ValueError("look_back_days must be >= 1.")

    # Pad start a few days to absorb weekends / holidays inside the window.
    start_dt = curr_dt - timedelta(days=look_back_days + 5)

    _, gl, _ = get_news_locale(ticker)
    local_index, local_label = _INDEX_BY_REGION.get(gl, _INDEX_BY_REGION["US"])

    sections = [
        f"# Market context for {ticker} as of {curr_date} (region={gl}, window={look_back_days}d)",
        _probe_market_index(local_index, f"Local index: {local_label}", start_dt, curr_dt),
    ]
    for sym, label in _GLOBAL_PROBES:
        sections.append(_probe_market_index(sym, label, start_dt, curr_dt))
    return "\n\n".join(sections)


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Get insider transactions data from yfinance.

    Yahoo Finance only exposes the most recent ~6 months of insider activity;
    it does **not** archive older transactions. For ``curr_date`` more than 6
    months in the past, this tool refuses rather than risk leaking present-day
    insider rows into a back-dated run.

    Args:
        ticker (str): Ticker symbol of the company.
        curr_date (str | None, optional): Current date used as a point-in-time
            boundary when transaction date columns are available. Defaults to None.

    Returns:
        str: CSV string containing insider transactions data, or a no-data
        message when the request is older than the available horizon.
    """
    horizon_message = _insider_history_unavailable_message(ticker, curr_date)
    if horizon_message is not None:
        return horizon_message

    as_of = _as_of_datetime(curr_date)
    candidates = get_yfinance_symbol_candidates(ticker)
    data = pd.DataFrame()
    resolved_ticker = candidates[0]
    last_error: Exception | None = None
    fetched_any_candidate = False

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            candidate_data = ticker_obj.insider_transactions
        except Exception as exc:
            logger.debug("Failed to fetch insider transactions for %s", candidate, exc_info=True)
            last_error = exc
            continue
        fetched_any_candidate = True
        if candidate_data is None or candidate_data.empty:
            continue
        candidate_data = _filter_insider_by_date(candidate_data, as_of)
        if not candidate_data.empty:
            data = candidate_data
            resolved_ticker = candidate
            break

    if data.empty:
        tried = describe_symbol_candidates(ticker, candidates)
        if not fetched_any_candidate and last_error is not None:
            raise RuntimeError(
                f"Failed to fetch insider transactions for symbol '{ticker}' (tried: {tried})"
            ) from last_error
        return (
            f"No insider transactions data found for symbol '{ticker}' (tried: {tried}) "
            f"as of {curr_date or 'latest'}"
        )

    csv_string = data.to_csv()

    header = f"# Insider Transactions data for {resolved_ticker}\n"
    if curr_date is not None:
        header += f"# Current trading date: {curr_date}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string
