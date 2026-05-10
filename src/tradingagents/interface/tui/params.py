"""Setup parameters shared between the Setup and Run screens.

Mirrors the keyword arguments of
:func:`tradingagents.interface.cli.run_cli` so the worker thread can
splat ``params.model_dump()`` straight into the construction of
:class:`tradingagents.config.TradingAgentsConfig` and
:class:`tradingagents.graph.trading_graph.TradingAgentsGraph`.
"""

from __future__ import annotations

import datetime

from pydantic import Field, BaseModel, field_validator

from tradingagents.llm import LLMProvider, ReasoningEffort  # noqa: TC001
from tradingagents.config import ResponseLanguage  # noqa: TC001
from tradingagents.graph.setup import SUPPORTED_ANALYSTS, GraphSetup


class SetupParams(BaseModel):
    """All parameters collected by :class:`SetupScreen` for a TUI run.

    Field defaults match :func:`tradingagents.interface.cli.run_cli`
    so pressing Start without editing reproduces the documented
    "all defaults" CLI invocation.
    """

    ticker: str = Field(
        default="GOOG", title="Ticker", description="Ticker symbol or company name to analyse."
    )
    date: str = Field(
        default_factory=lambda: datetime.date.today().strftime("%Y-%m-%d"),
        title="Trade Date",
        description="Trade date in YYYY-MM-DD format.",
    )
    llm_provider: LLMProvider = Field(
        default="google_genai",
        title="LLM Provider",
        description="LangChain init_chat_model registry key.",
    )
    deep_think_llm: str = Field(
        default="gemini-3.1-pro-preview",
        title="Deep Think LLM",
        description="Model name for the Research Manager and Risk Manager.",
    )
    quick_think_llm: str = Field(
        default="gemini-3-flash-preview",
        title="Quick Think LLM",
        description="Model name for analysts, researchers, trader and debaters.",
    )
    reasoning_effort: ReasoningEffort = Field(
        default="high",
        title="Reasoning Effort",
        description="Unified reasoning level (mapped per provider).",
    )
    response_language: ResponseLanguage = Field(
        default="zh-TW",
        title="Response Language",
        description="BCP 47 tag appended to every agent's prompt.",
    )
    selected_analysts: list[str] = Field(
        default_factory=lambda: list(SUPPORTED_ANALYSTS),
        title="Selected Analysts",
        description="Subset of market / social / news / fundamentals to include.",
    )
    max_debate_rounds: int = Field(
        default=10,
        ge=0,
        title="Max Debate Rounds",
        description="Maximum Bull/Bear investment debate rounds.",
    )
    max_risk_discuss_rounds: int = Field(
        default=10,
        ge=0,
        title="Max Risk Discuss Rounds",
        description="Maximum risk management debate rounds.",
    )
    max_recur_limit: int = Field(
        default=100,
        ge=25,
        title="Max Recursion Limit",
        description="Maximum LangGraph recursion limit (must be >= 25).",
    )
    debug: bool = Field(
        default=True,
        title="Debug",
        description="Stream agent messages live (forwarded to the underlying graph).",
    )

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: str) -> str:
        """Reject malformed or future trade dates.

        Args:
            value (str): The candidate trade date string.

        Returns:
            str: The validated date in YYYY-MM-DD format.

        Raises:
            ValueError: If the input is not parseable as YYYY-MM-DD or
                is in the future.
        """
        try:
            parsed = datetime.date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"date must be in YYYY-MM-DD format: {value!r}") from exc
        today = datetime.date.today()
        if parsed > today:
            raise ValueError(f"date cannot be in the future ({today})")
        return parsed.strftime("%Y-%m-%d")

    @field_validator("selected_analysts")
    @classmethod
    def _validate_analysts(cls, value: list[str]) -> list[str]:
        """Normalise and reject unknown / empty analyst lists.

        Delegates to :meth:`GraphSetup.validate_selected_analysts` so all
        three call sites (graph build, CLI, TUI) share one validator.
        """
        return GraphSetup.validate_selected_analysts(value)

    @field_validator("ticker")
    @classmethod
    def _validate_ticker(cls, value: str) -> str:
        """Strip whitespace and reject empty tickers.

        Args:
            value (str): The candidate ticker.

        Returns:
            str: The stripped ticker.

        Raises:
            ValueError: If the ticker is empty after stripping.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("ticker must not be empty")
        return stripped
