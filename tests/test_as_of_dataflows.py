from datetime import datetime

import pandas as pd
import pytest

from tradingagents.dataflows import news
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
