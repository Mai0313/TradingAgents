from enum import StrEnum
from pathlib import Path

from pydantic import Field, BaseModel

_PROJECT_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = Path("./results")
_DATA_CACHE_DIR = _PROJECT_DIR / "dataflows" / "data_cache"


class LLMProvider(StrEnum):
    """Supported LLM providers for TradingAgents."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    XAI = "xai"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"


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
    llm_provider: LLMProvider = Field(
        ...,
        title="LLM Provider",
        description="LLM provider to use. Must be one of the supported providers in LLMProvider enum.",
    )
    deep_think_llm: str = Field(
        ...,
        title="Deep Thinking LLM",
        description="Model name for deep thinking tasks (Research Manager, Risk Manager)",
    )
    quick_think_llm: str = Field(
        ...,
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
        ...,
        title="Max Debate Rounds",
        description="Maximum number of Bull/Bear investment debate rounds",
    )
    max_risk_discuss_rounds: int = Field(
        ...,
        title="Max Risk Discussion Rounds",
        description="Maximum number of risk management debate rounds",
    )
    max_recur_limit: int = Field(
        ...,
        ge=25,
        title="Max Recursion Limit",
        description="Maximum recursion limit for the LangGraph execution",
    )
