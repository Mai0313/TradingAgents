"""Provider adapter metadata for market-data and news backends."""

from typing import Literal

from pydantic import Field, BaseModel

ProviderDomain = Literal["market_data", "fundamentals", "news", "macro"]


class DataProviderAdapter(BaseModel):
    """Describes one data provider's point-in-time capabilities."""

    name: str = Field(..., title="Name", description="Stable provider adapter name.")
    domains: tuple[ProviderDomain, ...] = Field(
        ..., title="Domains", description="Data domains served by this provider."
    )
    point_in_time_safe: bool = Field(
        ...,
        title="Point-in-Time Safe",
        description="Whether the provider endpoint is historical point-in-time safe by default.",
    )
    limitations: str = Field(
        ...,
        title="Limitations",
        description="Human-readable caveats surfaced in docs and diagnostics.",
    )


YFINANCE_PROVIDER = DataProviderAdapter(
    name="yfinance",
    domains=("market_data", "fundamentals", "news", "macro"),
    point_in_time_safe=False,
    limitations=(
        "OHLCV and date-indexed event history can be filtered as-of; many snapshot "
        "endpoints expose only current provider state and must return [NO_DATA] for "
        "historical runs."
    ),
)

GOOGLE_NEWS_RSS_PROVIDER = DataProviderAdapter(
    name="google_news_rss",
    domains=("news",),
    point_in_time_safe=False,
    limitations=(
        "Free RSS search is a rolling feed, not a complete archive; results are "
        "filtered by publish date and treated as best-effort coverage."
    ),
)


def registered_provider_adapters() -> tuple[DataProviderAdapter, ...]:
    """Return built-in provider adapters in deterministic order."""
    return (YFINANCE_PROVIDER, GOOGLE_NEWS_RSS_PROVIDER)
