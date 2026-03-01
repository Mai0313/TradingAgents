import logging
from datetime import datetime
from dataclasses import dataclass

from dateutil.relativedelta import relativedelta

from .alpha_vantage_common import _make_api_request

logger = logging.getLogger(__name__)

SUPPORTED_INDICATORS = {
    "close_50_sma": ("50 SMA", "close"),
    "close_200_sma": ("200 SMA", "close"),
    "close_10_ema": ("10 EMA", "close"),
    "macd": ("MACD", "close"),
    "macds": ("MACD Signal", "close"),
    "macdh": ("MACD Histogram", "close"),
    "rsi": ("RSI", "close"),
    "boll": ("Bollinger Middle", "close"),
    "boll_ub": ("Bollinger Upper Band", "close"),
    "boll_lb": ("Bollinger Lower Band", "close"),
    "atr": ("ATR", None),
    "vwma": ("VWMA", "close"),
}

INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.",
    "close_200_sma": "200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.",
    "close_10_ema": "10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.",
    "macd": "MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.",
    "macds": "MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.",
    "macdh": "MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.",
    "rsi": "RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.",
    "boll": "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.",
    "boll_ub": "Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.",
    "boll_lb": "Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.",
    "atr": "ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.",
    "vwma": "VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.",
}

# CSV column name mapping (Alpha Vantage vs internal names)
_COL_NAME_MAP = {
    "macd": "MACD",
    "macds": "MACD_Signal",
    "macdh": "MACD_Hist",
    "boll": "Real Middle Band",
    "boll_ub": "Real Upper Band",
    "boll_lb": "Real Lower Band",
    "rsi": "RSI",
    "atr": "ATR",
    "close_10_ema": "EMA",
    "close_50_sma": "SMA",
    "close_200_sma": "SMA",
}


@dataclass
class IndicatorRequest:
    """Groups parameters for an indicator API request."""

    symbol: str
    interval: str
    time_period: int
    series_type: str


@dataclass
class IndicatorConfig:
    """Optional configuration for indicator requests."""

    interval: str = "daily"
    time_period: int = 14
    series_type: str = "close"


def get_indicator(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
    config: IndicatorConfig | None = None,
) -> str:
    """Returns Alpha Vantage technical indicator values over a time window.

    Args:
        symbol: ticker symbol of the company
        indicator: technical indicator to get the analysis and report of
        curr_date: The current trading date you are trading on, YYYY-mm-dd
        look_back_days: how many days to look back
        config: Optional IndicatorConfig for interval, time_period, and series_type

    Returns:
        String containing indicator values and description
    """
    if config is None:
        config = IndicatorConfig()

    if indicator not in SUPPORTED_INDICATORS:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(SUPPORTED_INDICATORS.keys())}"
        )

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    _, required_series_type = SUPPORTED_INDICATORS[indicator]
    series_type = required_series_type if required_series_type else config.series_type

    req = IndicatorRequest(
        symbol=symbol,
        interval=config.interval,
        time_period=config.time_period,
        series_type=series_type,
    )

    try:
        data = _fetch_indicator_data(indicator, req)

        if not isinstance(data, str):
            return f"Error: Unexpected data type from indicator fetch for {indicator}"

        lines = data.strip().split("\n")
        if len(lines) < 2:
            return f"Error: No data returned for {indicator}"

        header = [col.strip() for col in lines[0].split(",")]
        try:
            date_col_idx = header.index("time")
        except ValueError:
            return f"Error: 'time' column not found in data for {indicator}. Available columns: {header}"

        target_col_name = _COL_NAME_MAP.get(indicator)
        if not target_col_name:
            value_col_idx = 1
        else:
            try:
                value_col_idx = header.index(target_col_name)
            except ValueError:
                return f"Error: Column '{target_col_name}' not found for indicator '{indicator}'. Available columns: {header}"

        result_data = _parse_date_range(
            lines[1:], date_col_idx, value_col_idx, before, curr_date_dt
        )

        ind_string = (
            "".join(f"{dt.strftime('%Y-%m-%d')}: {val}\n" for dt, val in result_data)
            or "No data available for the specified date range.\n"
        )

        return (
            f"## {indicator.upper()} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
            + ind_string
            + "\n\n"
            + INDICATOR_DESCRIPTIONS.get(indicator, "No description available.")
        )

    except Exception as e:
        logger.error("Error getting Alpha Vantage indicator data for %s: %s", indicator, e)
        return f"Error retrieving {indicator} data: {e!s}"


def _parse_date_range(
    lines: list[str],
    date_col_idx: int,
    value_col_idx: int,
    before: datetime,
    curr_date_dt: datetime,
) -> list[tuple[datetime, str]]:
    """Parse CSV lines and return (date, value) pairs within the date range."""
    result_data: list[tuple[datetime, str]] = []
    for line in lines:
        if not line.strip():
            continue
        values = line.split(",")
        if len(values) <= value_col_idx:
            continue
        try:
            date_str = values[date_col_idx].strip()
            date_dt = datetime.strptime(date_str, "%Y-%m-%d")
            if before <= date_dt <= curr_date_dt:
                result_data.append((date_dt, values[value_col_idx].strip()))
        except (ValueError, IndexError):
            continue
    result_data.sort(key=lambda x: x[0])
    return result_data


def _fetch_indicator_data(indicator: str, req: IndicatorRequest) -> str:
    """Fetch indicator data from Alpha Vantage API.

    Returns a CSV string or early-return string for special cases.
    """
    dispatch: dict[str, tuple[str, dict[str, str]]] = {
        "close_50_sma": (
            "SMA",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "time_period": "50",
                "series_type": req.series_type,
                "datatype": "csv",
            },
        ),
        "close_200_sma": (
            "SMA",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "time_period": "200",
                "series_type": req.series_type,
                "datatype": "csv",
            },
        ),
        "close_10_ema": (
            "EMA",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "time_period": "10",
                "series_type": req.series_type,
                "datatype": "csv",
            },
        ),
        "macd": (
            "MACD",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "series_type": req.series_type,
                "datatype": "csv",
            },
        ),
        "macds": (
            "MACD",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "series_type": req.series_type,
                "datatype": "csv",
            },
        ),
        "macdh": (
            "MACD",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "series_type": req.series_type,
                "datatype": "csv",
            },
        ),
        "rsi": (
            "RSI",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "time_period": str(req.time_period),
                "series_type": req.series_type,
                "datatype": "csv",
            },
        ),
        "boll": (
            "BBANDS",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "time_period": "20",
                "series_type": req.series_type,
                "datatype": "csv",
            },
        ),
        "boll_ub": (
            "BBANDS",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "time_period": "20",
                "series_type": req.series_type,
                "datatype": "csv",
            },
        ),
        "boll_lb": (
            "BBANDS",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "time_period": "20",
                "series_type": req.series_type,
                "datatype": "csv",
            },
        ),
        "atr": (
            "ATR",
            {
                "symbol": req.symbol,
                "interval": req.interval,
                "time_period": str(req.time_period),
                "datatype": "csv",
            },
        ),
    }

    if indicator == "vwma":
        return (
            f"## VWMA (Volume Weighted Moving Average) for {req.symbol}:\n\n"
            f"VWMA calculation requires OHLCV data and is not directly available from Alpha Vantage API.\n"
            f"This indicator would need to be calculated from the raw stock data using volume-weighted price averaging.\n\n"
            f"{INDICATOR_DESCRIPTIONS.get('vwma', 'No description available.')}"
        )

    if indicator not in dispatch:
        return f"Error: Indicator {indicator} not implemented yet."

    function_name, params = dispatch[indicator]
    return _make_api_request(function_name, params)
