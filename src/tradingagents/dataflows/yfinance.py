from typing import Annotated
import logging
from pathlib import Path
from datetime import datetime

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


def _has_meaningful_ticker_info(info: dict) -> bool:
    """Return whether yfinance info contains an actual resolved quote."""
    identity_fields = ("longName", "shortName", "symbol", "quoteType", "market", "exchange")
    return any(info.get(field) for field in identity_fields)


def get_yfin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Fetch OHLCV stock data online via yfinance and return as CSV string."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    candidates = get_yfinance_symbol_candidates(symbol)

    data = pd.DataFrame()
    resolved_symbol = candidates[0]
    for candidate in candidates:
        try:
            ticker = yf.Ticker(candidate)
            candidate_data = ticker.history(start=start_date, end=end_date)
        except Exception:
            logger.debug("Failed to fetch history for %s", candidate, exc_info=True)
            continue
        if not candidate_data.empty:
            data = candidate_data
            resolved_symbol = candidate
            break

    # Check if data is empty
    if data.empty:
        tried = describe_symbol_candidates(symbol, candidates)
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

    end_date = curr_date
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    indicator_data = _get_stock_stats_bulk(symbol, indicator)

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
) -> dict[str, str]:
    """Fetch 15 years of OHLCV once and compute the indicator for every available date.

    Returns a dict mapping YYYY-MM-DD strings to indicator values.
    """
    config = get_config()

    today_date = pd.Timestamp.today()
    end_date = today_date
    start_date = today_date - pd.DateOffset(years=15)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    cache_dir = Path(str(config.data_cache_dir))
    cache_dir.mkdir(parents=True, exist_ok=True)

    candidates = get_yfinance_symbol_candidates(symbol)
    data = pd.DataFrame()

    for candidate in candidates:
        data_file = cache_dir / f"{candidate}-YFin-data-{start_date_str}-{end_date_str}.csv"
        if data_file.exists():
            candidate_data = pd.read_csv(data_file)
            candidate_data["Date"] = pd.to_datetime(candidate_data["Date"])
        else:
            try:
                candidate_data = yf.download(
                    candidate,
                    start=start_date_str,
                    end=end_date_str,
                    multi_level_index=False,
                    progress=False,
                    auto_adjust=True,
                )
            except Exception:
                logger.debug("Failed to download history for %s", candidate, exc_info=True)
                continue
            candidate_data = candidate_data.reset_index()
            candidate_data.to_csv(data_file, index=False)

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
    curr_date: Annotated[str | None, "current date (not used for yfinance)"] = None,
) -> str:
    """Get company fundamentals overview from yfinance."""
    try:
        candidates = get_yfinance_symbol_candidates(ticker)
        info = {}
        resolved_ticker = candidates[0]

        for candidate in candidates:
            try:
                ticker_obj = yf.Ticker(candidate)
                candidate_info = ticker_obj.info
            except Exception:
                logger.debug("Failed to fetch fundamentals for %s", candidate, exc_info=True)
                continue
            if _has_meaningful_ticker_info(candidate_info):
                info = candidate_info
                resolved_ticker = candidate
                break

        if not info:
            tried = describe_symbol_candidates(ticker, candidates)
            return f"No fundamentals data found for symbol '{ticker}' (tried: {tried})"

        fields = [
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

        lines = []
        for label, value in fields:
            if value is not None:
                lines.append(f"{label}: {value}")

        header = f"# Company Fundamentals for {resolved_ticker}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + "\n".join(lines)

    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {e!s}"


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str | None, "current date (not used for yfinance)"] = None,
) -> str:
    """Get balance sheet data from yfinance."""
    try:
        candidates = get_yfinance_symbol_candidates(ticker)
        data = pd.DataFrame()
        resolved_ticker = candidates[0]

        for candidate in candidates:
            try:
                ticker_obj = yf.Ticker(candidate)
                if freq.lower() == "quarterly":
                    candidate_data = ticker_obj.quarterly_balance_sheet
                else:
                    candidate_data = ticker_obj.balance_sheet
            except Exception:
                logger.debug("Failed to fetch balance sheet for %s", candidate, exc_info=True)
                continue
            if not candidate_data.empty:
                data = candidate_data
                resolved_ticker = candidate
                break

        if data.empty:
            tried = describe_symbol_candidates(ticker, candidates)
            return f"No balance sheet data found for symbol '{ticker}' (tried: {tried})"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Balance Sheet data for {resolved_ticker} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {e!s}"


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str | None, "current date (not used for yfinance)"] = None,
) -> str:
    """Get cash flow data from yfinance."""
    try:
        candidates = get_yfinance_symbol_candidates(ticker)
        data = pd.DataFrame()
        resolved_ticker = candidates[0]

        for candidate in candidates:
            try:
                ticker_obj = yf.Ticker(candidate)
                if freq.lower() == "quarterly":
                    candidate_data = ticker_obj.quarterly_cashflow
                else:
                    candidate_data = ticker_obj.cashflow
            except Exception:
                logger.debug("Failed to fetch cash flow for %s", candidate, exc_info=True)
                continue
            if not candidate_data.empty:
                data = candidate_data
                resolved_ticker = candidate
                break

        if data.empty:
            tried = describe_symbol_candidates(ticker, candidates)
            return f"No cash flow data found for symbol '{ticker}' (tried: {tried})"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Cash Flow data for {resolved_ticker} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {e!s}"


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str | None, "current date (not used for yfinance)"] = None,
) -> str:
    """Get income statement data from yfinance."""
    try:
        candidates = get_yfinance_symbol_candidates(ticker)
        data = pd.DataFrame()
        resolved_ticker = candidates[0]

        for candidate in candidates:
            try:
                ticker_obj = yf.Ticker(candidate)
                if freq.lower() == "quarterly":
                    candidate_data = ticker_obj.quarterly_income_stmt
                else:
                    candidate_data = ticker_obj.income_stmt
            except Exception:
                logger.debug("Failed to fetch income statement for %s", candidate, exc_info=True)
                continue
            if not candidate_data.empty:
                data = candidate_data
                resolved_ticker = candidate
                break

        if data.empty:
            tried = describe_symbol_candidates(ticker, candidates)
            return f"No income statement data found for symbol '{ticker}' (tried: {tried})"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Income Statement data for {resolved_ticker} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {e!s}"


def get_insider_transactions(ticker: Annotated[str, "ticker symbol of the company"]) -> str:
    """Get insider transactions data from yfinance."""
    try:
        candidates = get_yfinance_symbol_candidates(ticker)
        data = pd.DataFrame()
        resolved_ticker = candidates[0]

        for candidate in candidates:
            try:
                ticker_obj = yf.Ticker(candidate)
                candidate_data = ticker_obj.insider_transactions
            except Exception:
                logger.debug(
                    "Failed to fetch insider transactions for %s", candidate, exc_info=True
                )
                continue
            if candidate_data is not None and not candidate_data.empty:
                data = candidate_data
                resolved_ticker = candidate
                break

        if data is None or data.empty:
            tried = describe_symbol_candidates(ticker, candidates)
            return f"No insider transactions data found for symbol '{ticker}' (tried: {tried})"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Insider Transactions data for {resolved_ticker}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {e!s}"
