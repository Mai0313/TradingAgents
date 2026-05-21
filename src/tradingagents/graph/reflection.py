# TradingAgents/graph/reflection.py

import re
from typing import Literal, cast
import logging

from pydantic import Field, BaseModel, ConfigDict, SkipValidation
from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.content import flatten_message_content
from tradingagents.agents.utils.agent_states import AgentState

_REFLECTION_PROMPT_VERSION = "reflector-v1"
logger = logging.getLogger(__name__)

LessonCategory = Literal[
    "pattern_to_repeat", "hidden_mistake", "bad_luck", "lucky", "mistake_to_avoid"
]
_SCORE_LINE = re.compile(
    r"^-\s*(macro|technicals|price_action|news_flow|sentiment|fundamentals|"
    r"overall_reasoning|outcome_quality|lesson_category)\s*:\s*(.+?)\s*$",
    re.MULTILINE,
)
_NUMERIC_SCORE_KEYS = {
    "macro",
    "technicals",
    "price_action",
    "news_flow",
    "sentiment",
    "fundamentals",
    "overall_reasoning",
    "outcome_quality",
}
_LESSON_CATEGORIES = {
    "pattern_to_repeat",
    "hidden_mistake",
    "bad_luck",
    "lucky",
    "mistake_to_avoid",
}


class ReflectionOutcomeContext(BaseModel):
    """Structured trade-outcome fields supplied to the reflector."""

    entry_price: float | None = Field(
        default=None,
        title="Entry Price",
        description="Backtest entry close used for realised return scoring.",
    )
    exit_price: float | None = Field(
        default=None,
        title="Exit Price",
        description="Backtest exit close used for realised return scoring.",
    )
    exit_date: str | None = Field(
        default=None, title="Exit Date", description="Exit date used for realised return scoring."
    )
    horizon_days: int | None = Field(
        default=None,
        ge=1,
        title="Horizon Days",
        description="Configured backtest holding horizon in trading bars.",
    )
    benchmark_returns: dict[str, float] = Field(
        default_factory=dict,
        title="Benchmark Returns",
        description="Benchmark returns over the same entry / exit window.",
    )


class ReflectionScores(BaseModel):
    """Parsed numeric rubric emitted by the reflection prompt."""

    macro: int = Field(..., ge=1, le=5, title="Macro", description="Macro context score.")
    technicals: int = Field(
        ..., ge=1, le=5, title="Technicals", description="Technical indicator score."
    )
    price_action: int = Field(
        ..., ge=1, le=5, title="Price Action", description="Price-action score."
    )
    news_flow: int = Field(..., ge=1, le=5, title="News Flow", description="News-flow score.")
    sentiment: int = Field(..., ge=1, le=5, title="Sentiment", description="Sentiment score.")
    fundamentals: int = Field(
        ..., ge=1, le=5, title="Fundamentals", description="Fundamentals score."
    )
    overall_reasoning: int = Field(
        ..., ge=1, le=5, title="Overall Reasoning", description="Overall reasoning score."
    )
    outcome_quality: int = Field(
        ..., ge=1, le=5, title="Outcome Quality", description="Realised outcome score."
    )
    lesson_category: LessonCategory = Field(
        ..., title="Lesson Category", description="Structured lesson bucket."
    )


def _flatten_content(content: object) -> str:
    """Flatten a LangChain message ``.content`` value to a string.

    Anthropic Claude and Gemini 3 sometimes return list-shaped content
    (a list of ``{"type": "text", "text": "..."}`` chunks); BM25 then
    fails because ``"".lower()`` is not defined for lists. This
    normaliser is a single source of truth for that flattening.
    """
    return flatten_message_content(content)


def parse_reflection_scores(text: str) -> ReflectionScores | None:
    """Parse the required ``### Reflection scores`` block if present."""
    raw_values = {key: value.strip() for key, value in _SCORE_LINE.findall(text)}
    expected_keys = _NUMERIC_SCORE_KEYS | {"lesson_category"}
    if not expected_keys.issubset(raw_values):
        return None

    lesson_category = raw_values["lesson_category"]
    if lesson_category not in _LESSON_CATEGORIES:
        return None
    try:
        return ReflectionScores(
            macro=int(raw_values["macro"]),
            technicals=int(raw_values["technicals"]),
            price_action=int(raw_values["price_action"]),
            news_flow=int(raw_values["news_flow"]),
            sentiment=int(raw_values["sentiment"]),
            fundamentals=int(raw_values["fundamentals"]),
            overall_reasoning=int(raw_values["overall_reasoning"]),
            outcome_quality=int(raw_values["outcome_quality"]),
            lesson_category=cast("LessonCategory", lesson_category),
        )
    except (TypeError, ValueError):
        logger.debug("Failed to parse reflection scores", exc_info=True)
        return None


class Reflector(BaseModel):
    """Generates per-agent reflections used to update the BM25 memories."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    quick_thinking_llm: SkipValidation[ChatModel] = Field(
        ...,
        title="Quick Thinking LLM",
        description="LLM instance used for generating reflection analysis",
    )

    def _reflect_on_component(
        self,
        report: str,
        situation: str,
        returns_losses: float,
        outcome_context: str | None = None,
    ) -> str:
        """Generate a reflection paragraph for a single decision component.

        Args:
            report: The component's history / report / plan to reflect on.
            situation: The combined market situation snapshot.
            returns_losses: Realised P/L for the trade.
            outcome_context: Optional structured trade-outcome context.

        Returns:
            The reflector LLM's text response, flattened to a plain string.
        """
        outcome_block = outcome_context or f"Returns: {returns_losses}"
        messages = [
            SystemMessage(content=load_prompt("reflector")),
            HumanMessage(
                content=(
                    f"{outcome_block}\n\n"
                    f"Analysis/Decision: {report}\n\n"
                    f"Objective Market Reports for Reference: {situation}"
                )
            ),
        ]
        return _flatten_content(self.quick_thinking_llm.invoke(messages).content)

    @staticmethod
    def _stored_situation(current_state: AgentState) -> str:
        """Return the BM25-index document to store alongside the reflection.

        Future agents query memories with ``state.situation_summary``, so the
        document side must use the same shape. Fall back to the full
        ``combined_reports`` only when no summary was produced.
        """
        return current_state.situation_summary or current_state.combined_reports

    @staticmethod
    def _outcome_context(current_state: AgentState, returns_losses: float) -> str:
        """Return structured outcome text for the reflection prompt."""
        return Reflector._format_outcome_context(current_state, returns_losses, None)

    @staticmethod
    def _format_outcome_context(
        current_state: AgentState,
        returns_losses: float,
        outcome_context: ReflectionOutcomeContext | None,
    ) -> str:
        """Return structured outcome text for the reflection prompt."""
        recommendation = current_state.final_trade_recommendation
        if recommendation is None:
            recommendation_text = "unavailable"
        else:
            recommendation_text = recommendation.model_dump_json()
        lines = [
            f"Returns: {returns_losses}",
            "# Structured outcome",
            f"- ticker: {current_state.company_of_interest}",
            f"- trade_date: {current_state.trade_date}",
            f"- final_recommendation: {recommendation_text}",
        ]
        if outcome_context is not None:
            lines.extend([
                f"- entry_price: {outcome_context.entry_price}",
                f"- exit_price: {outcome_context.exit_price}",
                f"- exit_date: {outcome_context.exit_date}",
                f"- horizon_days: {outcome_context.horizon_days}",
                f"- benchmark_returns: {outcome_context.benchmark_returns}",
            ])
        return "\n".join(lines)

    @staticmethod
    def _memory_metadata(
        current_state: AgentState, returns_losses: float, component: str
    ) -> dict[str, object]:
        """Return JSONL metadata stored alongside one reflection lesson."""
        recommendation = current_state.final_trade_recommendation
        return {
            "ticker": current_state.company_of_interest,
            "trade_date": current_state.trade_date,
            "signal": recommendation.signal if recommendation is not None else "",
            "realised_return": returns_losses,
            "component": component,
            "prompt_version": _REFLECTION_PROMPT_VERSION,
        }

    def reflect_bull_researcher(
        self,
        current_state: AgentState,
        returns_losses: float,
        bull_memory: FinancialSituationMemory,
        outcome_context: ReflectionOutcomeContext | None = None,
    ) -> ReflectionScores | None:
        """Reflect on the bull researcher's history and update its memory."""
        result = self._reflect_on_component(
            current_state.investment_debate_state.bull_history,
            current_state.combined_reports,
            returns_losses,
            self._format_outcome_context(current_state, returns_losses, outcome_context),
        )
        bull_memory.add_situations([
            (
                self._stored_situation(current_state),
                result,
                self._memory_metadata(current_state, returns_losses, "bull_researcher"),
            )
        ])
        return parse_reflection_scores(result)

    def reflect_bear_researcher(
        self,
        current_state: AgentState,
        returns_losses: float,
        bear_memory: FinancialSituationMemory,
        outcome_context: ReflectionOutcomeContext | None = None,
    ) -> ReflectionScores | None:
        """Reflect on the bear researcher's history and update its memory."""
        result = self._reflect_on_component(
            current_state.investment_debate_state.bear_history,
            current_state.combined_reports,
            returns_losses,
            self._format_outcome_context(current_state, returns_losses, outcome_context),
        )
        bear_memory.add_situations([
            (
                self._stored_situation(current_state),
                result,
                self._memory_metadata(current_state, returns_losses, "bear_researcher"),
            )
        ])
        return parse_reflection_scores(result)

    def reflect_trader(
        self,
        current_state: AgentState,
        returns_losses: float,
        trader_memory: FinancialSituationMemory,
        outcome_context: ReflectionOutcomeContext | None = None,
    ) -> ReflectionScores | None:
        """Reflect on the trader's plan and update its memory."""
        result = self._reflect_on_component(
            current_state.trader_investment_plan,
            current_state.combined_reports,
            returns_losses,
            self._format_outcome_context(current_state, returns_losses, outcome_context),
        )
        trader_memory.add_situations([
            (
                self._stored_situation(current_state),
                result,
                self._memory_metadata(current_state, returns_losses, "trader"),
            )
        ])
        return parse_reflection_scores(result)

    def reflect_invest_judge(
        self,
        current_state: AgentState,
        returns_losses: float,
        invest_judge_memory: FinancialSituationMemory,
        outcome_context: ReflectionOutcomeContext | None = None,
    ) -> ReflectionScores | None:
        """Reflect on the research-manager verdict and update its memory."""
        result = self._reflect_on_component(
            current_state.investment_debate_state.judge_decision,
            current_state.combined_reports,
            returns_losses,
            self._format_outcome_context(current_state, returns_losses, outcome_context),
        )
        invest_judge_memory.add_situations([
            (
                self._stored_situation(current_state),
                result,
                self._memory_metadata(current_state, returns_losses, "investment_judge"),
            )
        ])
        return parse_reflection_scores(result)

    def reflect_risk_manager(
        self,
        current_state: AgentState,
        returns_losses: float,
        risk_manager_memory: FinancialSituationMemory,
        outcome_context: ReflectionOutcomeContext | None = None,
    ) -> ReflectionScores | None:
        """Reflect on the risk-manager verdict and update its memory."""
        result = self._reflect_on_component(
            current_state.risk_debate_state.judge_decision,
            current_state.combined_reports,
            returns_losses,
            self._format_outcome_context(current_state, returns_losses, outcome_context),
        )
        risk_manager_memory.add_situations([
            (
                self._stored_situation(current_state),
                result,
                self._memory_metadata(current_state, returns_losses, "risk_manager"),
            )
        ])
        return parse_reflection_scores(result)
