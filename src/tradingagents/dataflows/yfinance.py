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


def _read_cached_history(data_file: Path) -> pd.DataFrame:
    """Read a cached yfinance history CSV."""
    candidate_data = pd.read_csv(data_file)
    candidate_data["Date"] = pd.to_datetime(candidate_data["Date"])
    return candidate_data


def _download_history(candidate: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Download raw OHLCV history for a symbol candidate."""
    try:
        candidate_data = yf.download(
            candidate,
            start=start_date,
            end=end_date,
            multi_level_index=False,
            progress=False,
            auto_adjust=False,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to download history for {candidate}") from exc
    return candidate_data.reset_index()


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
    """Fetch OHLCV stock data online via yfinance and return as CSV string.

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
    _validate_date_range(start_date, end_date)

    candidates = get_yfinance_symbol_candidates(symbol)

    data = pd.DataFrame()
    resolved_symbol = candidates[0]
    last_error: Exception | None = None
    fetched_any_candidate = False
    for candidate in candidates:
        try:
            ticker = yf.Ticker(candidate)
            candidate_data = ticker.history(start=start_date, end=end_date, auto_adjust=False)
        except Exception as exc:
            logger.debug("Failed to fetch history for %s", candidate, exc_info=True)
            last_error = exc
            continue
        fetched_any_candidate = True
        if not candidate_data.empty:
            data = candidate_data
            resolved_symbol = candidate
            break

    # Check if data is empty
    if data.empty:
        tried = describe_symbol_candidates(symbol, candidates)
        if not fetched_any_candidate and last_error is not None:
            raise RuntimeError(
                f"Failed to fetch market data for symbol '{symbol}' (tried: {tried})"
            ) from last_error
        return f"No data found for symbol '{symbol}' (tried: {tried}) between {start_date} and {end_date}"

    # Remove timezone info from index for cleaner output
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    # Round numerical values to 2 decimal places for cleaner display
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    # Convert DataFrame to CSV string
    csv_string = data.to_csv()

    # Add header information
    header = f"# Stock data for {resolved_symbol} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Calculate and format a specific technical indicator over a window of days.

    Args:
        symbol (str): Ticker symbol of the company.
        indicator (str): Technical indicator to calculate.
        curr_date (str): Current trading date in YYYY-MM-DD format.
        look_back_days (int): Number of days to look back.

    Returns:
        str: Formatted string containing indicator values and a description.

    Raises:
        ValueError: If the requested indicator is not supported, `curr_date`
            does not match YYYY-MM-DD, the symbol is empty, or no market data is
            available.
    """
    best_ind_params = {
        # Moving Averages
        "close_50_sma": (
            "50 SMA: A medium-term trend indicator. "
            "Usage: Identify trend direction and serve as dynamic support/resistance. "
            "Tips: It lags price; combine with faster indicators for timely signals."
        ),
        "close_200_sma": (
            "200 SMA: A long-term trend benchmark. "
            "Usage: Confirm overall market trend and identify golden/death cross setups. "
            "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
        ),
        "close_10_ema": (
            "10 EMA: A responsive short-term average. "
            "Usage: Capture quick shifts in momentum and potential entry points. "
            "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
        ),
        # MACD Related
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
            "Usage: Visualize momentum strength and spot divergence early. "
            "Tips: Can be volatile; complement with additional filters in fast-moving markets."
        ),
        # Momentum Indicators
        "rsi": (
            "RSI: Measures momentum to flag overbought/oversold conditions. "
            "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
            "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
        ),
        # Volatility Indicators
        "boll": (
            "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
            "Usage: Acts as a dynamic benchmark for price movement. "
            "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
        ),
        "boll_ub": (
            "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
            "Usage: Signals potential overbought conditions and breakout zones. "
            "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
        ),
        "boll_lb": (
            "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
            "Usage: Indicates potential oversold conditions. "
            "Tips: Use additional analysis to avoid false reversal signals."
        ),
        "atr": (
            "ATR: Averages true range to measure volatility. "
            "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
            "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
        ),
        # Volume-Based Indicators
        "vwma": (
            "VWMA: A moving average weighted by volume. "
            "Usage: Confirm trends by integrating price action with volume data. "
            "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
        ),
        "mfi": (
            "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
            "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
            "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
        ),
    }

    if indicator not in best_ind_params:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(best_ind_params.keys())}"
        )

    if look_back_days < 0:
        raise ValueError("look_back_days must be >= 0.")

    end_date = curr_date
    curr_date_dt = _parse_yyyy_mm_dd(curr_date, "curr_date")
    before = curr_date_dt - relativedelta(days=look_back_days)

    indicator_data = _get_stock_stats_bulk(symbol, indicator, curr_date)

    current_dt = curr_date_dt
    ind_string = ""
    while current_dt >= before:
        date_str = current_dt.strftime("%Y-%m-%d")
        value = indicator_data.get(date_str, "N/A: Not a trading day (weekend or holiday)")
        ind_string += f"{date_str}: {value}\n"
        current_dt = current_dt - relativedelta(days=1)

    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "No description available.")
    )


def _get_stock_stats_bulk(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "current trading date in YYYY-MM-DD format"],
) -> dict[str, str]:
    """Fetch 15 years of OHLCV once and compute the indicator for every available date.

    Args:
        symbol (str): Ticker symbol of the company.
        indicator (str): Technical indicator to calculate.
        curr_date (str): Current trading date in YYYY-MM-DD format.

    Returns:
        dict[str, str]: A dict mapping YYYY-MM-DD strings to indicator values.

    Raises:
        ValueError: If the symbol is empty or no market data is found.
        RuntimeError: If the global TradingAgentsConfig has not been initialized.
    """
    config = get_config()

    curr_date_dt = _parse_yyyy_mm_dd(curr_date, "curr_date")
    end_date = pd.Timestamp(curr_date_dt + timedelta(days=1))
    start_date = pd.Timestamp(curr_date_dt) - pd.DateOffset(years=15)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    cache_dir = Path(str(config.data_cache_dir))
    cache_dir.mkdir(parents=True, exist_ok=True)

    candidates = get_yfinance_symbol_candidates(symbol)
    data = pd.DataFrame()

    for candidate in candidates:
        data_file = cache_dir / f"{candidate}-YFin-data-{start_date_str}-{end_date_str}.csv"
        use_cache = data_file.exists() and curr_date_dt.date() < datetime.now().date()
        candidate_data = _load_history_candidate(
            candidate, data_file, start_date_str, end_date_str, use_cache=use_cache
        )

        if not candidate_data.empty:
            data = candidate_data
            break

    if data.empty:
        tried = describe_symbol_candidates(symbol, candidates)
        raise ValueError(f"No market data found for symbol '{symbol}' (tried: {tried}).")

    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # Calculate the indicator for all rows at once
    df[indicator]  # This triggers stockstats to calculate the indicator

    # Create a dictionary mapping date strings to indicator values
    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        indicator_value = row[indicator]

        # Handle NaN/None values
        if pd.isna(indicator_value):
            result_dict[date_str] = "N/A"
        else:
            result_dict[date_str] = str(indicator_value)

    return result_dict


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

    candidates = get_yfinance_symbol_candidates(ticker)
    info = {}
    resolved_ticker = candidates[0]
    last_error: Exception | None = None
    fetched_any_candidate = False

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            candidate_info = ticker_obj.info
        except Exception as exc:
            logger.debug("Failed to fetch fundamentals for %s", candidate, exc_info=True)
            last_error = exc
            continue
        fetched_any_candidate = True
        if _has_meaningful_ticker_info(candidate_info):
            info = candidate_info
            resolved_ticker = candidate
            break

    if not info:
        tried = describe_symbol_candidates(ticker, candidates)
        if not fetched_any_candidate and last_error is not None:
            raise RuntimeError(
                f"Failed to fetch fundamentals for symbol '{ticker}' (tried: {tried})"
            ) from last_error
        return f"No fundamentals data found for symbol '{ticker}' (tried: {tried})"

    profile_fields = [
        ("Name", info.get("longName")),
        ("Sector", info.get("sector")),
        ("Industry", info.get("industry")),
    ]
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
        if value is not None:
            lines.append(f"{label}: {value}")

    header = f"# Company Fundamentals for {resolved_ticker}\n"
    if curr_date is not None:
        header += f"# Current trading date: {curr_date}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    if _is_historical_date(curr_date):
        header += (
            "# Snapshot valuation/market metrics omitted: yfinance.info only "
            "provides current values, not point-in-time historical values.\n"
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

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            candidate_data = (
                ticker_obj.quarterly_balance_sheet
                if freq == "quarterly"
                else ticker_obj.balance_sheet
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch balance sheet for {candidate}") from exc
        candidate_data = _filter_statement_as_of(candidate_data, curr_date, freq)
        if not candidate_data.empty:
            data = candidate_data
            resolved_ticker = candidate
            break

    if data.empty:
        tried = describe_symbol_candidates(ticker, candidates)
        return (
            f"No balance sheet data found for symbol '{ticker}' (tried: {tried}) "
            f"as of {curr_date or 'latest'}"
        )

    csv_string = data.to_csv()

    header = f"# Balance Sheet data for {resolved_ticker} ({freq})\n"
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

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            candidate_data = (
                ticker_obj.quarterly_cashflow if freq == "quarterly" else ticker_obj.cashflow
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch cash flow for {candidate}") from exc
        candidate_data = _filter_statement_as_of(candidate_data, curr_date, freq)
        if not candidate_data.empty:
            data = candidate_data
            resolved_ticker = candidate
            break

    if data.empty:
        tried = describe_symbol_candidates(ticker, candidates)
        return (
            f"No cash flow data found for symbol '{ticker}' (tried: {tried}) "
            f"as of {curr_date or 'latest'}"
        )

    csv_string = data.to_csv()

    header = f"# Cash Flow data for {resolved_ticker} ({freq})\n"
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

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            candidate_data = (
                ticker_obj.quarterly_income_stmt if freq == "quarterly" else ticker_obj.income_stmt
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch income statement for {candidate}") from exc
        candidate_data = _filter_statement_as_of(candidate_data, curr_date, freq)
        if not candidate_data.empty:
            data = candidate_data
            resolved_ticker = candidate
            break

    if data.empty:
        tried = describe_symbol_candidates(ticker, candidates)
        return (
            f"No income statement data found for symbol '{ticker}' (tried: {tried}) "
            f"as of {curr_date or 'latest'}"
        )

    csv_string = data.to_csv()

    header = f"# Income Statement data for {resolved_ticker} ({freq})\n"
    header += _statement_as_of_note(curr_date, freq)
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str | None, "current trading date in YYYY-MM-DD format"] = None,
) -> str:
    """Get insider transactions data from yfinance.

    Args:
        ticker (str): Ticker symbol of the company.
        curr_date (str | None, optional): Current date used as a point-in-time
            boundary when transaction date columns are available. Defaults to None.

    Returns:
        str: CSV string containing insider transactions data.
    """
    as_of = _as_of_datetime(curr_date)
    candidates = get_yfinance_symbol_candidates(ticker)
    data = pd.DataFrame()
    resolved_ticker = candidates[0]

    for candidate in candidates:
        try:
            ticker_obj = yf.Ticker(candidate)
            candidate_data = ticker_obj.insider_transactions
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch insider transactions for {candidate}") from exc
        if candidate_data is None or candidate_data.empty:
            continue
        if as_of is not None:
            date_columns = [
                column for column in candidate_data.columns if "date" in str(column).lower()
            ]
            if date_columns:
                dates = pd.to_datetime(candidate_data[date_columns[0]], errors="coerce")
                candidate_data = candidate_data.loc[dates <= pd.Timestamp(as_of)]
        if not candidate_data.empty:
            data = candidate_data
            resolved_ticker = candidate
            break

    if data.empty:
        tried = describe_symbol_candidates(ticker, candidates)
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
