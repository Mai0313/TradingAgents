from typing import Literal
from pathlib import Path

from pydantic import Field, BaseModel, computed_field

LLMProvider = Literal["openai", "anthropic", "google", "xai", "ollama", "openrouter"]
"""Supported LLM providers for TradingAgents."""

ReasoningEffort = Literal["low", "medium", "high", "max"]
"""Unified reasoning effort levels, mapped per-provider at the client layer.

Provider mappings:
- OpenAI:       low -> low,  medium -> medium, high -> high, max -> xhigh
- Google:       low -> low,  medium -> medium, high -> high, max -> high
                (Gemini 2.5 uses thinking_budget: low/medium disabled, high/max dynamic)
                (Gemini 3 Pro lacks medium; it falls back to low)
- Anthropic:    low -> low,  medium -> medium, high -> high, max -> max
"""


class TradingAgentsConfig(BaseModel):
    """Configuration for the TradingAgents framework."""

    results_dir: Path = Field(
        default=Path("./results"),
        title="Results Directory",
        description="Directory for saving analysis results",
    )

    llm_provider: LLMProvider = Field(
        ...,
        title="LLM Provider",
        description="LLM provider to use. Must be one of the supported providers.",
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
    reasoning_effort: ReasoningEffort = Field(
        default="medium",
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

    @computed_field(
        title="Data Cache Directory",
        description="Directory for caching downloaded data (automatically placed under results_dir)",
    )
    @property
    def data_cache_dir(self) -> Path:
        data_cache_dir = self.results_dir / "data_cache"
        return data_cache_dir
