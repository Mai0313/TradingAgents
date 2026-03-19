from pathlib import Path

from pydantic import Field, BaseModel

_PROJECT_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = Path("./results")
_DATA_CACHE_DIR = _PROJECT_DIR / "dataflows" / "data_cache"


class DataVendorsConfig(BaseModel):
    """Category-level data vendor configuration."""

    core_stock_apis: str = Field(
        default="yfinance",
        title="Core Stock APIs Vendor",
        description="Data vendor for OHLCV stock price data. Options: yfinance, alpha_vantage",
    )
    technical_indicators: str = Field(
        default="yfinance",
        title="Technical Indicators Vendor",
        description="Data vendor for technical analysis indicators. Options: yfinance, alpha_vantage",
    )
    fundamental_data: str = Field(
        default="yfinance",
        title="Fundamental Data Vendor",
        description="Data vendor for company fundamentals. Options: yfinance, alpha_vantage",
    )
    news_data: str = Field(
        default="yfinance",
        title="News Data Vendor",
        description="Data vendor for news and insider data. Options: yfinance, alpha_vantage",
    )


class TradingAgentsConfig(BaseModel):
    """Configuration for the TradingAgents framework."""

    project_dir: Path = Field(
        default=_PROJECT_DIR,
        title="Project Directory",
        description="Root directory of the tradingagents package",
    )
    results_dir: Path = Field(
        default=_RESULTS_DIR,
        title="Results Directory",
        description="Directory for saving analysis results",
    )
    data_cache_dir: Path = Field(
        default=_DATA_CACHE_DIR,
        title="Data Cache Directory",
        description="Directory for caching downloaded data",
    )
    llm_provider: str = Field(
        default="openai",
        title="LLM Provider",
        description="LLM provider to use. Options: openai, anthropic, google, xai, ollama, openrouter",
    )
    deep_think_llm: str = Field(
        default="gpt-5.2",
        title="Deep Thinking LLM",
        description="Model name for deep thinking tasks (Research Manager, Risk Manager)",
    )
    quick_think_llm: str = Field(
        default="gpt-5-mini",
        title="Quick Thinking LLM",
        description="Model name for quick thinking tasks (analysts, researchers, trader, debators)",
    )
    backend_url: str = Field(
        default="https://api.openai.com/v1",
        title="Backend URL",
        description="Base URL for the LLM API endpoint",
    )
    google_thinking_level: str | None = Field(
        default=None,
        title="Google Thinking Level",
        description="Thinking level for Google Gemini models (e.g. 'high', 'minimal')",
    )
    openai_reasoning_effort: str | None = Field(
        default=None,
        title="OpenAI Reasoning Effort",
        description="Reasoning effort for OpenAI models (e.g. 'low', 'medium', 'high')",
    )
    max_debate_rounds: int = Field(
        default=1,
        title="Max Debate Rounds",
        description="Maximum number of Bull/Bear investment debate rounds",
    )
    max_risk_discuss_rounds: int = Field(
        default=1,
        title="Max Risk Discussion Rounds",
        description="Maximum number of risk management debate rounds",
    )
    max_recur_limit: int = Field(
        default=100,
        title="Max Recursion Limit",
        description="Maximum recursion limit for the LangGraph execution",
    )
    data_vendors: DataVendorsConfig = Field(
        default_factory=DataVendorsConfig,
        title="Data Vendors",
        description="Category-level data vendor configuration",
    )
    tool_vendors: dict[str, str] = Field(
        default_factory=dict,
        title="Tool Vendors",
        description="Tool-level vendor overrides (takes precedence over category-level)",
    )


DEFAULT_CONFIG = TradingAgentsConfig()
