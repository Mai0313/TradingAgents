from types import SimpleNamespace
from pathlib import Path
from datetime import datetime

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


def test_get_yfin_data_online_treats_end_date_as_inclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    class FakeTicker:
        def __init__(self, candidate: str) -> None:
            self.candidate = candidate

        def history(self, *, start: str, end: str, auto_adjust: bool) -> pd.DataFrame:
            seen["start"] = start
            seen["end"] = end
            seen["auto_adjust"] = str(auto_adjust)
            return pd.DataFrame(
                {
                    "Open": [1.0],
                    "High": [2.0],
                    "Low": [0.5],
                    "Close": [1.5],
                    "Adj Close": [1.5],
                    "Volume": [100],
                },
                index=pd.DatetimeIndex([pd.Timestamp("2024-01-01")]),
            )

    monkeypatch.setattr(yfinance_data, "get_yfinance_symbol_candidates", lambda symbol: ["AAPL"])
    monkeypatch.setattr(yfinance_data.yf, "Ticker", FakeTicker)

    result = yfinance_data.get_yfin_data_online("AAPL", "2024-01-01", "2024-01-01")

    assert seen == {"start": "2024-01-01", "end": "2024-01-02", "auto_adjust": "False"}
    assert "# Total records: 1" in result


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
    class FakeTicker:
        def __init__(self, candidate: str) -> None:
            self.candidate = candidate

        @property
        def insider_transactions(self) -> pd.DataFrame:
            if self.candidate == "BAD":
                raise RuntimeError("candidate failed")
            return pd.DataFrame({"Start Date": [pd.Timestamp("2024-01-01")], "Shares": [10]})

    monkeypatch.setattr(
        yfinance_data, "get_yfinance_symbol_candidates", lambda ticker: ["BAD", "GOOD"]
    )
    monkeypatch.setattr(yfinance_data.yf, "Ticker", FakeTicker)

    result = yfinance_data.get_insider_transactions("BRK.A", curr_date="2024-02-01")

    assert "# Insider Transactions data for GOOD" in result


def test_stock_stats_bulk_continues_after_candidate_load_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

    result = yfinance_data._get_stock_stats_bulk("BRK.A", "close_10_ema", "2024-01-03")

    assert calls == ["BAD", "GOOD"]
    assert "2024-01-03" in result


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


def test_get_news_yfinance_returns_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_fetch_error(ticker: str) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr(news, "_get_first_ticker_news", raise_fetch_error)

    result = news.get_news_yfinance("AAPL", "2024-01-01", "2024-01-01")

    assert result == "Error fetching news for AAPL: network down"


def test_get_global_news_yfinance_returns_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingSearch:
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("search down")

    monkeypatch.setattr(news.yf, "Search", FailingSearch)

    result = news.get_global_news_yfinance("2024-01-01")

    assert (
        result
        == "Error fetching global news: Failed to fetch global news from Yahoo Finance: search down"
    )
