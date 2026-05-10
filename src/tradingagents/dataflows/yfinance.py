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


def _is_cache_usable(data_file: Path, curr_date_dt: datetime) -> bool:
    """Return whether the on-disk cache should be reused for ``curr_date``.

    Historical (back-dated) runs always reuse the cache; today's run only
    reuses it if the file was written within ``_CACHE_FRESH_HOURS`` hours.
    """
    if not data_file.exists():
        return False
    if curr_date_dt.date() < datetime.now().date():
        return True
    age = datetime.now() - datetime.fromtimestamp(data_file.stat().st_mtime)
    return age < timedelta(hours=_CACHE_FRESH_HOURS)


def _load_history_candidate(
    candidate: str, data_file: Path, start_date: str, end_date: str, *, use_cache: bool
) -> pd.DataFrame:
    """Load cached history when safe, otherwise download and refresh cache."""
    candidate_data = pd.DataFrame()
    if use_cache:
        try:
            candidate_data = _read_cached_history(data_file)
        except Exception:
            logger.warning("Ignoring unreadable cache file %s", data_file, exc_info=True)

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
    (which feeds it through stockstats), so a single download per
    ``(symbol, curr_date)`` services every market-analyst tool call.

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

    end_date = pd.Timestamp(curr_date_dt + timedelta(days=1))
    start_date = pd.Timestamp(curr_date_dt) - pd.DateOffset(years=15)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    cache_dir = Path(str(config.data_cache_dir))
    cache_dir.mkdir(parents=True, exist_ok=True)

    candidates = get_yfinance_symbol_candidates(symbol)
    data = pd.DataFrame()
    resolved_symbol = candidates[0]
    last_error: Exception | None = None
    fetched_any_candidate = False

    for candidate in candidates:
        data_file = cache_dir / f"{candidate}-YFin-data-{start_date_str}-{end_date_str}.csv"
        use_cache = _is_cache_usable(data_file, curr_date_dt)
        try:
            candidate_data = _load_history_candidate(
                candidate, data_file, start_date_str, end_date_str, use_cache=use_cache
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
        "Tips: Pair with +DI/-DI to confirm direction; not useful in choppy markets."
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


def _get_stock_stats_bulk_multi(
    symbol: str, indicators: list[str], curr_date: str
) -> tuple[str, dict[str, dict[str, str]]]:
    """Resolve history once and compute every indicator in ``indicators``.

    Args:
        symbol: User-supplied ticker.
        indicators: List of stockstats indicator names; all assumed to be in
            :data:`BEST_IND_PARAMS`.
        curr_date: Current trading date in YYYY-MM-DD format.

    Returns:
        ``(resolved_symbol, {indicator: {YYYY-MM-DD: value_str}})``.

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
    return resolved_symbol, result


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

    _, data_map = _get_stock_stats_bulk_multi(symbol, indicators, curr_date)

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
    return "\n\n".join(sections)


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


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Get company fundamentals overview from yfinance.

    Args:
        ticker (str): Ticker symbol of the company.
        curr_date (str | None, optional): Current date used as a point-in-time
            boundary. Current yfinance snapshot metrics are omitted for
            historical dates because Yahoo Finance does not expose their
            historical availability through this endpoint. Defaults to None.

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

    fields = profile_fields if _is_historical_date(curr_date) else snapshot_fields
    lines = []
    for label, value in fields:
        if value is None:
            continue
        if label in big_number_fields:
            lines.append(f"{label}: {_humanize_number(value)}")
        else:
            lines.append(f"{label}: {value}")

    header = f"# Company Fundamentals for {resolved_ticker}\n"
    if curr_date is not None:
        header += f"# Current trading date: {curr_date}\n"
    header += f"# Reporting currency (info.financialCurrency): {info.get('financialCurrency') or 'UNKNOWN'}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    if _is_historical_date(curr_date):
        header += (
            "# Snapshot valuation/market metrics omitted: yfinance.info only "
            "provides current values, not point-in-time historical values.\n"
            "# For historical revenue, EPS, and balance-sheet context call "
            "get_income_statement / get_balance_sheet / get_cashflow with "
            "curr_date set -- those endpoints ARE point-in-time-filtered.\n"
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


_INSIDER_HISTORY_HORIZON_DAYS = 180


def _insider_history_unavailable_message(ticker: str, curr_date: str | None) -> str | None:
    """Return a no-data message if curr_date is older than yfinance's horizon."""
    as_of = _as_of_datetime(curr_date)
    if as_of is None:
        return None
    horizon = datetime.now().date() - timedelta(days=_INSIDER_HISTORY_HORIZON_DAYS)
    if as_of.date() >= horizon:
        return None
    return (
        f"# Insider Transactions data for {ticker}\n"
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
