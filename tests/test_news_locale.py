from types import SimpleNamespace
from typing import Any

import pytest

from tradingagents.dataflows import news
from tradingagents.dataflows.tickers import get_news_locale
import tradingagents.dataflows.yfinance as yfinance_data
from tradingagents.dataflows.providers import registered_provider_adapters


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("AAPL", ("en-US", "US", "US:en")),
        ("2330.TW", ("zh-TW", "TW", "TW:zh-Hant")),
        ("8069.TWO", ("zh-TW", "TW", "TW:zh-Hant")),
        ("7203.T", ("ja-JP", "JP", "JP:ja")),
        ("0700.HK", ("zh-HK", "HK", "HK:zh-Hant")),
        ("600519.SS", ("zh-CN", "CN", "CN:zh-Hans")),
        ("000333.SZ", ("zh-CN", "CN", "CN:zh-Hans")),
        ("SAP.DE", ("de-DE", "DE", "DE:de")),
        ("005930.KS", ("ko-KR", "KR", "KR:ko")),
        ("VOD.L", ("en-GB", "GB", "GB:en")),
        ("ASML.AS", ("nl-NL", "NL", "NL:nl")),
        ("BHP.AX", ("en-AU", "AU", "AU:en")),
        ("RY.TO", ("en-CA", "CA", "CA:en")),
        ("UNKNOWN.XYZ", ("en-US", "US", "US:en")),  # unmapped suffix → default
    ],
)
def test_get_news_locale_resolves_suffix(symbol: str, expected: tuple[str, str, str]) -> None:
    assert get_news_locale(symbol) == expected


def test_registered_provider_adapters_include_current_free_sources() -> None:
    adapters = {adapter.name: adapter for adapter in registered_provider_adapters()}

    assert {"yfinance", "google_news_rss"} <= set(adapters)
    assert "news" in adapters["google_news_rss"].domains
    assert adapters["yfinance"].limitations


def test_get_news_locale_resolves_bare_digit_symbol_to_taiwan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tradingagents.dataflows.tickers.get_yfinance_symbol_candidates",
        lambda symbol: ["2330.TW", "2330"],
    )

    assert get_news_locale("2330") == ("zh-TW", "TW", "TW:zh-Hant")


def test_market_context_uses_resolved_bare_digit_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    probed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "tradingagents.dataflows.tickers.get_yfinance_symbol_candidates",
        lambda symbol: ["2330.TW", "2330"],
    )

    def fake_probe(symbol: str, label: str, *args: object) -> str:
        probed.append((symbol, label))
        return f"## {label} ({symbol})"

    monkeypatch.setattr(yfinance_data, "_probe_market_index", fake_probe)

    result = yfinance_data.get_market_context("2330", "2024-01-05", look_back_days=5)

    assert "region=TW" in result
    assert probed[0][0] == "^TWII"


def test_google_news_rss_uses_locale_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_news_google_rss`` must substitute the resolved (hl, gl, ceid) into the URL."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(news, "_resolve_company_name_for_news", lambda ticker: None)

    def fake_feedparser_parse(url: str) -> SimpleNamespace:
        captured["url"] = url
        return SimpleNamespace(entries=[])

    monkeypatch.setattr(news.feedparser, "parse", fake_feedparser_parse)

    result = news.get_news_google_rss("2330.TW", "2024-01-01", "2024-01-02")

    assert "hl=zh-TW" in captured["url"]
    assert "gl=TW" in captured["url"]
    assert "ceid=TW%3Azh-Hant" in captured["url"] or "ceid=TW:zh-Hant" in captured["url"]
    # The result is a no-data message because no entries were returned.
    assert result.startswith("[NO_DATA]")


def test_google_news_rss_defaults_to_en_us_for_bare_us_ticker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(news, "_resolve_company_name_for_news", lambda ticker: None)

    def fake_feedparser_parse(url: str) -> SimpleNamespace:
        captured["url"] = url
        return SimpleNamespace(entries=[])

    monkeypatch.setattr(news.feedparser, "parse", fake_feedparser_parse)

    news.get_news_google_rss("AAPL", "2024-01-01", "2024-01-02")

    assert "hl=en-US" in captured["url"]
    assert "gl=US" in captured["url"]


def test_google_news_rss_falls_back_to_company_name_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news, "_resolve_company_name_for_news", lambda ticker: "Apple Inc.")
    parsed_urls: list[str] = []
    entry = SimpleNamespace(
        title="Apple earnings preview",
        link="https://example.test/apple",
        published_parsed=(2024, 1, 2, 10, 0, 0, 1, 2, 0),
        source={"title": "Example"},
    )

    def fake_feedparser_parse(url: str) -> SimpleNamespace:
        parsed_urls.append(url)
        if "Apple+Inc." in url:
            return SimpleNamespace(entries=[entry])
        return SimpleNamespace(entries=[])

    monkeypatch.setattr(news.feedparser, "parse", fake_feedparser_parse)

    result = news.get_news_google_rss("AAPL", "2024-01-01", "2024-01-03")

    assert len(parsed_urls) == 2
    assert "AAPL+stock" in parsed_urls[0]
    assert "Apple+Inc.+stock" in parsed_urls[1]
    assert "Apple earnings preview" in result
    assert "query='Apple Inc. stock'" in result
