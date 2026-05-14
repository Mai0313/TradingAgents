from typing import Annotated

from pydantic import Field, BaseModel, ConfigDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from tradingagents.graph.signal_processing import TradeRecommendation


class InvestDebateState(BaseModel):
    """State for the Bull/Bear investment research debate."""

    bull_history: str = Field(
        default="",
        title="Bull History",
        description="Cumulative debate transcript from the bull researcher",
    )
    bear_history: str = Field(
        default="",
        title="Bear History",
        description="Cumulative debate transcript from the bear researcher",
    )
    history: str = Field(
        default="", title="History", description="Complete combined debate transcript"
    )
    current_response: str = Field(
        default="", title="Current Response", description="Latest response in the debate"
    )
    judge_decision: str = Field(
        default="",
        title="Judge Decision",
        description="Final decision made by the research manager",
    )
    count: int = Field(default=0, title="Count", description="Number of debate turns completed")


class RiskDebateState(BaseModel):
    """State for the three-way risk management debate."""

    aggressive_history: str = Field(
        default="",
        title="Aggressive History",
        description="Cumulative debate transcript from the aggressive analyst",
    )
    conservative_history: str = Field(
        default="",
        title="Conservative History",
        description="Cumulative debate transcript from the conservative analyst",
    )
    neutral_history: str = Field(
        default="",
        title="Neutral History",
        description="Cumulative debate transcript from the neutral analyst",
    )
    history: str = Field(
        default="", title="History", description="Complete combined risk debate transcript"
    )
    latest_speaker: str = Field(
        default="",
        title="Latest Speaker",
        description="Name of the analyst who spoke most recently",
    )
    current_aggressive_response: str = Field(
        default="",
        title="Current Aggressive Response",
        description="Latest response from the aggressive analyst",
    )
    current_conservative_response: str = Field(
        default="",
        title="Current Conservative Response",
        description="Latest response from the conservative analyst",
    )
    current_neutral_response: str = Field(
        default="",
        title="Current Neutral Response",
        description="Latest response from the neutral analyst",
    )
    judge_decision: str = Field(
        default="", title="Judge Decision", description="Final decision made by the risk manager"
    )
    count: int = Field(default=0, title="Count", description="Number of debate turns completed")


class AgentState(BaseModel):
    """Full shared state passed between all nodes in the LangGraph workflow."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # --- Conversation history (reduced by add_messages) ---
    messages: Annotated[list[AnyMessage], add_messages] = Field(
        default_factory=list,
        title="Messages",
        description="Conversation history shared across all agent nodes",
    )

    # --- Core identifiers ---
    company_of_interest: str = Field(
        default="",
        title="Company of Interest",
        description="Ticker symbol or company name being analyzed",
    )
    trade_date: str = Field(
        default="",
        title="Trade Date",
        description="The date on which the trading decision is being made",
    )

    # --- Analyst reports ---
    market_report: str = Field(
        default="",
        title="Market Report",
        description="Technical analysis report produced by the Market Analyst",
    )
    sentiment_report: str = Field(
        default="",
        title="Sentiment Report",
        description="Social sentiment report produced by the Social Media Analyst",
    )
    news_report: str = Field(
        default="",
        title="News Report",
        description="News analysis report produced by the News Analyst",
    )
    fundamentals_report: str = Field(
        default="",
        title="Fundamentals Report",
        description="Fundamentals report produced by the Fundamentals Analyst",
    )

    # --- Cross-analyst synthesis ---
    situation_summary: str = Field(
        default="",
        title="Situation Summary",
        description=(
            "Compact (≤400 token) distilled snapshot of the four analyst reports "
            "produced by the Situation Summariser node. Used as the BM25 retrieval "
            "query for every memory.get_memories() call so retrieval signal is not "
            "diluted by the full multi-KB combined_reports payload."
        ),
    )

    # --- Research debate ---
    investment_debate_state: InvestDebateState = Field(
        default_factory=InvestDebateState,
        title="Investment Debate State",
        description="Running state of the Bull/Bear investment debate",
    )
    investment_plan: str = Field(
        default="",
        title="Investment Plan",
        description="Investment plan produced by the Research Manager",
    )
    trader_investment_plan: str = Field(
        default="",
        title="Trader Investment Plan",
        description="Trading plan produced by the Trader",
    )

    # --- Risk debate ---
    risk_debate_state: RiskDebateState = Field(
        default_factory=RiskDebateState,
        title="Risk Debate State",
        description="Running state of the three-way risk debate",
    )
    final_trade_decision: str = Field(
        default="",
        title="Final Trade Decision",
        description="Final BUY/SELL/HOLD decision produced by the Risk Manager",
    )
    final_trade_recommendation: TradeRecommendation | None = Field(
        default=None,
        title="Final Trade Recommendation",
        description=(
            "Structured Risk-Manager output (signal, size, target, stop, horizon, "
            "confidence, rationale). Populated by TradingAgentsGraph.propagate after "
            "signal extraction; None until the run completes."
        ),
    )

    @property
    def combined_reports(self) -> str:
        """Return the four analyst reports concatenated for memory queries.

        Used by every node that performs BM25 retrieval against the
        situation snapshot (researchers, managers, trader, reflector).
        """
        return (
            f"{self.market_report}\n\n"
            f"{self.sentiment_report}\n\n"
            f"{self.news_report}\n\n"
            f"{self.fundamentals_report}"
        )


__all__ = ["AgentState", "InvestDebateState", "RiskDebateState"]
