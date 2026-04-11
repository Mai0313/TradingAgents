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


class ReasoningEffort(StrEnum):
    """Unified reasoning effort levels, mapped per-provider at the client layer.

    Provider mappings:
    - OpenAI:    low -> low,  medium -> medium, high -> high, max -> xhigh
    - Google:    low -> LOW,  medium -> MEDIUM, high -> HIGH, max -> HIGH
                 (Gemini 2.5 uses thinking_budget: low/medium disabled, high/max dynamic)
                 (Gemini 3 Pro lacks medium; it falls back to LOW)
    - Anthropic: low -> low,  medium -> medium, high -> high, max -> max
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


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
    reasoning_effort: ReasoningEffort | None = Field(
        default=None,
        title="Reasoning Effort",
        description=(
            "Unified reasoning effort level for reasoning-capable LLMs. "
            "Mapped per-provider at the client layer (see ReasoningEffort docstring)."
        ),
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
