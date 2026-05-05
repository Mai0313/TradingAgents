# TradingAgents/graph/propagation.py

from typing import Any
from datetime import date

from pydantic import Field, BaseModel
from langchain_core.messages import HumanMessage

from tradingagents.agents.utils.agent_states import AgentState


class Propagator(BaseModel):
    max_recur_limit: int = Field(
        default=100,
        title="Max Recursion Limit",
        description="Maximum number of recursive calls allowed in the LangGraph execution",
    )

    def create_initial_state(self, company_name: str, trade_date: str) -> AgentState:
        """Create the initial AgentState for the graph execution.

        Args:
            company_name (str): The name of the company or ticker symbol.
            trade_date (str): The trade date in YYYY-MM-DD format.

        Returns:
            AgentState: The initialized agent state.
        """
        try:
            parsed_date = date.fromisoformat(str(trade_date))
        except ValueError as exc:
            raise ValueError(f"trade_date must be in YYYY-MM-DD format: {trade_date!r}") from exc
        today = date.today()
        if parsed_date > today:
            raise ValueError(f"trade_date cannot be in the future: {parsed_date} > {today}")

        return AgentState(
            messages=[HumanMessage(content=company_name)],
            company_of_interest=company_name,
            trade_date=parsed_date.strftime("%Y-%m-%d"),
        )

    def get_graph_args(self, callbacks: list | None = None) -> dict[str, Any]:
        """Get arguments for the graph invocation.

        Note: LLM callbacks are handled separately via LLM constructor.

        Args:
            callbacks (list | None, optional): Optional list of callback handlers for tool execution tracking. Defaults to None.

        Returns:
            dict[str, Any]: A dictionary containing stream mode and config arguments for graph execution.
        """
        config: dict[str, Any] = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {"stream_mode": "values", "config": config}
