from types import SimpleNamespace
from typing import Any

import pytest

from tradingagents.dataflows import news
from tradingagents.dataflows.tickers import get_news_locale


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("AAPL", ("en-US", "US", "US:en")),
        ("2330", ("en-US", "US", "US:en")),  # bare digits — no suffix yet
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


def test_google_news_rss_uses_locale_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_news_google_rss`` must substitute the resolved (hl, gl, ceid) into the URL."""
    captured: dict[str, Any] = {}

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

    def fake_feedparser_parse(url: str) -> SimpleNamespace:
        captured["url"] = url
        return SimpleNamespace(entries=[])

    monkeypatch.setattr(news.feedparser, "parse", fake_feedparser_parse)

    news.get_news_google_rss("AAPL", "2024-01-01", "2024-01-02")

    assert "hl=en-US" in captured["url"]
    assert "gl=US" in captured["url"]
