from types import SimpleNamespace
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import pytest

from tradingagents.dataflows import news
import tradingagents.dataflows.yfinance as yfinance_data
from tradingagents.dataflows.yfinance import _normalize_freq, _filter_statement_as_of


def test_filter_statement_as_of_uses_reporting_lag() -> None:
    data = pd.DataFrame(
        {pd.Timestamp("2024-03-31"): [1], pd.Timestamp("2024-06-30"): [2]}, index=["Total Revenue"]
    )

    filtered = _filter_statement_as_of(data, "2024-05-20", "quarterly")

    assert list(filtered.columns) == [pd.Timestamp("2024-03-31")]


def test_filter_statement_as_of_returns_empty_when_no_period_was_available() -> None:
    data = pd.DataFrame({pd.Timestamp("2024-03-31"): [1]}, index=["Total Revenue"])

    filtered = _filter_statement_as_of(data, "2024-04-15", "quarterly")

    assert filtered.empty


def test_get_yfin_data_online_slices_from_shared_history_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_yfin_data_online now reads the shared 15-y cache and slices the requested window.

    The previous test verified the live yfinance call directly; the new
    implementation goes through ``_resolve_history_with_cache`` so a single
    download services both the OHLCV tool and the indicator pipeline.
    """
    seen: dict[str, object] = {}

    fake_history = pd.DataFrame({
        "Date": pd.to_datetime(["2023-12-31", "2024-01-01", "2024-01-02"]),
        "Open": [0.9, 1.0, 1.1],
        "High": [1.9, 2.0, 2.1],
        "Low": [0.4, 0.5, 0.6],
        "Close": [1.4, 1.5, 1.6],
        "Adj Close": [1.4, 1.5, 1.6],
        "Volume": [90, 100, 110],
    })

    def fake_resolve(symbol: str, curr_date_dt: datetime) -> tuple[str, pd.DataFrame, list[str]]:
        seen["symbol"] = symbol
        seen["curr_date_dt"] = curr_date_dt
        return ("AAPL", fake_history.copy(), ["AAPL"])

    monkeypatch.setattr(yfinance_data, "_resolve_history_with_cache", fake_resolve)

    result = yfinance_data.get_yfin_data_online("AAPL", "2024-01-01", "2024-01-01")

    assert seen["symbol"] == "AAPL"
    assert seen["curr_date_dt"] == datetime(2024, 1, 1)
    # Window slice must include 2024-01-01 only, dropping 2023-12-31 and 2024-01-02.
    assert "# Total records: 1" in result
    assert "2024-01-01" in result
    assert "2023-12-31" not in result
    assert "2024-01-02" not in result
    # The header now advertises split- / dividend-adjusted prices.
    assert "auto_adjust=True" in result or "split- and dividend-adjusted" in result


@pytest.mark.parametrize(
    ("function_name", "expected_header"),
    [
        ("get_balance_sheet", "# Balance Sheet data for GOOD"),
        ("get_cashflow", "# Cash Flow data for GOOD"),
        ("get_income_statement", "# Income Statement data for GOOD"),
    ],
)
def test_statement_fetches_continue_after_candidate_exception(
    monkeypatch: pytest.MonkeyPatch, function_name: str, expected_header: str
) -> None:
    statement_data = pd.DataFrame({pd.Timestamp("2024-03-31"): [1]}, index=["Reported Value"])

    class FakeTicker:
        def __init__(self, candidate: str) -> None:
            self.candidate = candidate

        def _statement(self) -> pd.DataFrame:
            if self.candidate == "BAD":
                raise RuntimeError("candidate failed")
            return statement_data

        @property
        def quarterly_balance_sheet(self) -> pd.DataFrame:
            return self._statement()

        @property
        def quarterly_cashflow(self) -> pd.DataFrame:
            return self._statement()

        @property
        def quarterly_income_stmt(self) -> pd.DataFrame:
            return self._statement()

    monkeypatch.setattr(
        yfinance_data, "get_yfinance_symbol_candidates", lambda ticker: ["BAD", "GOOD"]
    )
    monkeypatch.setattr(yfinance_data.yf, "Ticker", FakeTicker)

    result = getattr(yfinance_data, function_name)("BRK.A", curr_date="2024-06-01")

    assert expected_header in result


def test_insider_transactions_continue_after_candidate_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Use a date inside the insider history horizon so the lookahead-bias
    # short-circuit (`_insider_history_unavailable_message`) does not preempt
    # the candidate-fallthrough loop we are actually testing.
    near_date = (datetime.now().date() - timedelta(days=30)).strftime("%Y-%m-%d")
    near_timestamp = pd.Timestamp(near_date)

    class FakeTicker:
        def __init__(self, candidate: str) -> None:
            self.candidate = candidate

        @property
        def insider_transactions(self) -> pd.DataFrame:
            if self.candidate == "BAD":
                raise RuntimeError("candidate failed")
            return pd.DataFrame({"Start Date": [near_timestamp], "Shares": [10]})

    monkeypatch.setattr(
        yfinance_data, "get_yfinance_symbol_candidates", lambda ticker: ["BAD", "GOOD"]
    )
    monkeypatch.setattr(yfinance_data.yf, "Ticker", FakeTicker)

    result = yfinance_data.get_insider_transactions("BRK.A", curr_date=near_date)

    assert "# Insider Transactions data for GOOD" in result


def test_stock_stats_bulk_multi_continues_after_candidate_load_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The single-indicator helper was replaced by ``_get_stock_stats_bulk_multi``
    in the indicator-batching refactor; this test now exercises the new helper.
    """
    calls: list[str] = []

    def fake_load_history_candidate(
        candidate: str, data_file: Path, start_date: str, end_date: str, *, use_cache: bool
    ) -> pd.DataFrame:
        calls.append(candidate)
        if candidate == "BAD":
            raise RuntimeError("download failed")
        return pd.DataFrame({
            "Date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "Open": [1.0, 1.2],
            "High": [1.5, 1.6],
            "Low": [0.9, 1.1],
            "Close": [1.3, 1.4],
            "Volume": [100, 120],
        })

    monkeypatch.setattr(
        yfinance_data, "get_config", lambda: SimpleNamespace(data_cache_dir=tmp_path)
    )
    monkeypatch.setattr(
        yfinance_data, "get_yfinance_symbol_candidates", lambda symbol: ["BAD", "GOOD"]
    )
    monkeypatch.setattr(yfinance_data, "_load_history_candidate", fake_load_history_candidate)

    resolved, data_map = yfinance_data._get_stock_stats_bulk_multi(
        "BRK.A", ["close_10_ema"], "2024-01-03"
    )

    assert calls == ["BAD", "GOOD"]
    assert resolved == "GOOD"
    assert "2024-01-03" in data_map["close_10_ema"]


def test_normalize_freq_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="quarterly"):
        _normalize_freq("monthly")


def test_extract_article_data_parses_flat_provider_publish_time() -> None:
    article = {
        "title": "Market update",
        "publisher": "Example",
        "providerPublishTime": 1_704_067_200,
    }

    extracted = news._extract_article_data(article)

    assert extracted["pub_date"] == datetime.fromtimestamp(1_704_067_200)


def test_get_news_yfinance_skips_undated_and_future_articles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    articles = [
        {"title": "In window", "publisher": "Example", "providerPublishTime": 1_704_067_200},
        {"title": "Undated", "publisher": "Example"},
        {"title": "Future", "publisher": "Example", "providerPublishTime": 1_704_412_800},
    ]

    monkeypatch.setattr(
        news, "_get_first_ticker_news", lambda ticker: ("AAPL", articles, ["AAPL"])
    )

    result = news.get_news_yfinance("AAPL", "2024-01-01", "2024-01-01")

    assert "In window" in result
    assert "Undated" not in result
    assert "Future" not in result


def test_get_news_yfinance_returns_tool_error_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    """News fetch errors must surface a ``[TOOL_ERROR]`` sentinel that the prompt
    layer can react to deterministically (rather than treating the traceback
    string as ordinary text).
    """

    def raise_fetch_error(ticker: str) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr(news, "_get_first_ticker_news", raise_fetch_error)

    result = news.get_news_yfinance("AAPL", "2024-01-01", "2024-01-01")

    assert result.startswith("[TOOL_ERROR]")
    assert "AAPL" in result
    assert "network down" in result


def test_get_global_news_yfinance_returns_tool_error_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same ``[TOOL_ERROR]`` sentinel contract on the global-news path."""

    class FailingSearch:
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("search down")

    monkeypatch.setattr(news.yf, "Search", FailingSearch)

    result = news.get_global_news_yfinance("2024-01-01")

    assert result.startswith("[TOOL_ERROR]")
    assert "search down" in result
