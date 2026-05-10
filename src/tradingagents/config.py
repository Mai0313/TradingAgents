from typing import Literal
from pathlib import Path
from contextvars import ContextVar

from pydantic import Field, BaseModel, computed_field

from tradingagents.llm import LLMProvider, ReasoningEffort

ResponseLanguage = Literal[
    "zh-TW",  # Traditional Chinese
    "zh-CN",  # Simplified Chinese
    "en-US",  # English (United States)
    "ja-JP",  # Japanese
    "ko-KR",  # Korean
    "de-DE",  # German
]


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
        description=(
            "Langchain `init_chat_model` registry key shared by both deep- and "
            "quick-thinking models (e.g. `openai`, `anthropic`, `google_genai`)."
        ),
    )
    deep_think_llm: str = Field(
        ...,
        title="Deep Thinking LLM",
        description=(
            "Model name for deep-thinking nodes (Research Manager, Risk Manager). "
            "Example: `claude-sonnet-4-6`, `gpt-5.4`."
        ),
    )
    quick_think_llm: str = Field(
        ...,
        title="Quick Thinking LLM",
        description=(
            "Model name for quick-thinking nodes (analysts, researchers, trader, debaters)."
        ),
    )
    reasoning_effort: ReasoningEffort = Field(
        default="medium",
        title="Reasoning Effort",
        description=(
            "Unified reasoning effort level for reasoning-capable LLMs. "
            "Mapped per-provider inside build_chat_model."
        ),
    )
    response_language: ResponseLanguage = Field(
        default="en-US",
        title="Response Language",
        description=(
            "BCP 47 language tag (ISO 639-1 + ISO 3166-1 alpha-2) appended "
            "to agent prompts. Supported values: zh-TW, zh-CN, en-US, "
            "ja-JP, ko-KR, de-DE."
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
        """Return the data cache directory under the results directory.

        Returns:
            Path: Directory used for caching downloaded market and news data.
        """
        data_cache_dir = self.results_dir / "data_cache"
        return data_cache_dir


_active_config: ContextVar[TradingAgentsConfig | None] = ContextVar(
    "tradingagents_active_config", default=None
)


def set_config(config: TradingAgentsConfig) -> None:
    """Register the active TradingAgentsConfig for cross-module access.

    Backed by :class:`contextvars.ContextVar` so concurrent graphs (e.g.
    notebook batch runs, async tasks) each see their own configuration
    instead of racing over one shared module-level slot.

    Args:
        config (TradingAgentsConfig): The configuration object to set as active.
    """
    _active_config.set(config)


def get_config() -> TradingAgentsConfig:
    """Return the active TradingAgentsConfig (set by TradingAgentsGraph).

    Returns:
        TradingAgentsConfig: The active configuration object.

    Raises:
        RuntimeError: If the TradingAgentsConfig has not been initialized yet.
    """
    cfg = _active_config.get()
    if cfg is None:
        raise RuntimeError(
            "TradingAgentsConfig has not been initialized. "
            "Construct a TradingAgentsConfig and pass it to TradingAgentsGraph "
            "(or call set_config) before accessing the global config."
        )
    return cfg
