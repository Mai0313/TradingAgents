"""Derive run-phase progress from a streaming :class:`AgentState`.

The TUI's left sidebar lights up phases (Market Analyst, Bull/Bear
debate, Trader, Risk debate, ...) as the LangGraph pipeline produces
them. Rather than hooking into individual graph nodes, this module
infers the running / done state from which AgentState fields the
streamed snapshots have populated. Every :func:`derive_phases` call is
pure: same state -> same phase list, no hidden mutation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field, BaseModel

if TYPE_CHECKING:
    from tradingagents.agents.utils.agent_states import AgentState

PhaseStatus = Literal["pending", "running", "done"]

ANALYST_PHASE_LABELS: dict[str, str] = {
    "market": "Market Analyst",
    "social": "News Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}

ANALYST_REPORT_FIELDS: dict[str, str] = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}


class Phase(BaseModel):
    """One row in the TUI phase sidebar.

    Attributes:
        id (str): Stable identifier (used as the widget DOM id, so it
            must be valid CSS / Python).
        label (str): Human-readable label rendered in the sidebar.
        status (PhaseStatus): One of "pending", "running", "done".
        progress (str): Optional secondary line, e.g. "3/10" for a
            debate counter. Empty string when there is no progress
            display.
    """

    id: str = Field(..., title="ID", description="Stable identifier; used as the DOM widget id.")
    label: str = Field(..., title="Label", description="Human-readable phase label.")
    status: PhaseStatus = Field(
        default="pending",
        title="Status",
        description="Lifecycle state: pending (not started), running (in progress), done.",
    )
    progress: str = Field(
        default="",
        title="Progress",
        description="Optional progress text (e.g. '3/10' for debate rounds).",
    )


def derive_phases(
    state: AgentState | None,
    *,
    selected_analysts: list[str],
    max_debate_rounds: int,
    max_risk_discuss_rounds: int,
) -> list[Phase]:
    """Map an :class:`AgentState` snapshot to a list of phase rows.

    The order encodes the actual graph topology in
    ``GraphSetup.setup_graph``: selected analysts run sequentially,
    then the Bull/Bear research debate, the Research Manager, the
    Trader, the three-way Risk debate, and finally the Risk Judge.

    Status inference:

    - Each analyst is "done" once its report field is non-empty,
      "running" iff every preceding phase is done, "pending" otherwise.
    - Bull/Bear debate uses ``investment_debate_state.count`` as the
      progress counter and is "done" only when ``judge_decision`` is set.
    - Research Manager done iff ``investment_plan`` is non-empty.
    - Trader done iff ``trader_investment_plan`` is non-empty.
    - Risk debate uses ``risk_debate_state.count`` similarly.
    - Final done iff ``final_trade_decision`` is non-empty.

    Args:
        state (AgentState | None): The latest streamed AgentState, or
            None before the first chunk arrives.
        selected_analysts (list[str]): Subset of {"market", "social",
            "news", "fundamentals"} to include as separate analyst
            phases.
        max_debate_rounds (int): Maximum Bull/Bear debate rounds, used
            for the "N/M" progress display.
        max_risk_discuss_rounds (int): Maximum risk-debate rounds.

    Returns:
        list[Phase]: One row per pipeline phase, in topological order.
    """
    phases: list[Phase] = []

    for analyst in selected_analysts:
        field = ANALYST_REPORT_FIELDS.get(analyst)
        label = ANALYST_PHASE_LABELS.get(analyst, analyst.title())
        phases.append(Phase(id=f"phase-{analyst}", label=label, progress=""))
        if state is not None and field is not None:
            value = getattr(state, field, "") or ""
            if value.strip():
                phases[-1] = phases[-1].model_copy(update={"status": "done"})

    summariser_done = bool(state is not None and (state.situation_summary or "").strip())
    phases.append(
        Phase(
            id="phase-situation-summary",
            label="Situation Summariser",
            status="done" if summariser_done else "pending",
        )
    )

    invest = state.investment_debate_state if state is not None else None
    invest_count = invest.count if invest is not None else 0
    invest_done = bool(invest is not None and (invest.judge_decision or "").strip())
    phases.append(
        Phase(
            id="phase-research-debate",
            label="Bull/Bear Debate",
            status="done" if invest_done else "pending",
            progress=f"{invest_count}/{max_debate_rounds}" if max_debate_rounds else "",
        )
    )

    research_done = bool(state is not None and (state.investment_plan or "").strip())
    phases.append(
        Phase(
            id="phase-research-manager",
            label="Research Manager",
            status="done" if research_done else "pending",
        )
    )

    trader_done = bool(state is not None and (state.trader_investment_plan or "").strip())
    phases.append(
        Phase(id="phase-trader", label="Trader", status="done" if trader_done else "pending")
    )

    risk = state.risk_debate_state if state is not None else None
    risk_count = risk.count if risk is not None else 0
    final_done = bool(state is not None and (state.final_trade_decision or "").strip())
    phases.append(
        Phase(
            id="phase-risk-debate",
            label="Risk Debate",
            status="done" if final_done else "pending",
            progress=f"{risk_count}/{max_risk_discuss_rounds}" if max_risk_discuss_rounds else "",
        )
    )

    phases.append(
        Phase(id="phase-final", label="Final Decision", status="done" if final_done else "pending")
    )

    # Promote the first non-done phase to "running" so the UI shows where
    # the pipeline currently is. If everything is done, leave it alone.
    for phase in phases:
        if phase.status != "done":
            phase.status = "running"
            break

    return phases
