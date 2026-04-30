from pathlib import Path

from pydantic import Field, BaseModel, computed_field

from tradingagents.llm import LLMProvider, ReasoningEffort


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
            "Model name for quick-thinking nodes "
            "(analysts, researchers, trader, debators)."
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


_config_container: list[TradingAgentsConfig | None] = [None]


def set_config(config: TradingAgentsConfig) -> None:
    """Register the active TradingAgentsConfig for cross-module access."""
    _config_container[0] = config


def get_config() -> TradingAgentsConfig:
    """Return the active TradingAgentsConfig (set by TradingAgentsGraph)."""
    cfg = _config_container[0]
    if cfg is None:
        raise RuntimeError(
            "TradingAgentsConfig has not been initialized. "
            "Construct a TradingAgentsConfig and pass it to TradingAgentsGraph "
            "(or call set_config) before accessing the global config."
        )
    return cfg
