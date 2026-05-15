# TradingAgents/graph/setup.py

from typing import Any

from pydantic import Field, BaseModel, ConfigDict, SkipValidation
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.graph.state import CompiledStateGraph

from tradingagents.llm import ChatModel
from tradingagents.agents import (
    AgentState,
    create_trader,
    create_msg_delete,
    create_news_analyst,
    create_risk_manager,
    create_market_analyst,
    create_bear_researcher,
    create_bull_researcher,
    create_neutral_debator,
    create_research_manager,
    create_aggressive_debator,
    create_conservative_debator,
    create_fundamentals_analyst,
    create_situation_summariser,
    create_social_media_analyst,
)
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.tool_registry import ANALYST_TOOL_REGISTRY

from .conditional_logic import ConditionalLogic

SUPPORTED_ANALYSTS = tuple(ANALYST_TOOL_REGISTRY)


class MemoryComponents(BaseModel):
    """Groups all memory components for the trading agents."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bull: FinancialSituationMemory = Field(
        ..., title="Bull Memory", description="Memory store for the bull researcher agent"
    )
    bear: FinancialSituationMemory = Field(
        ..., title="Bear Memory", description="Memory store for the bear researcher agent"
    )
    trader: FinancialSituationMemory = Field(
        ..., title="Trader Memory", description="Memory store for the trader agent"
    )
    invest_judge: FinancialSituationMemory = Field(
        ...,
        title="Investment Judge Memory",
        description="Memory store for the investment judge agent",
    )
    risk_manager: FinancialSituationMemory = Field(
        ..., title="Risk Manager Memory", description="Memory store for the risk manager agent"
    )


class GraphSetup(BaseModel):
    """Handles the setup and configuration of the agent graph."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # --- User-configurable fields ---

    quick_thinking_llm: SkipValidation[ChatModel] = Field(
        ...,
        title="Quick Thinking LLM",
        description="LLM instance used for analyst and researcher nodes",
    )
    deep_thinking_llm: SkipValidation[ChatModel] = Field(
        ...,
        title="Deep Thinking LLM",
        description="LLM instance used for manager and judge nodes requiring deeper reasoning",
    )
    tool_nodes: dict[str, ToolNode] = Field(
        ...,
        title="Tool Nodes",
        description="Mapping of analyst type to its corresponding LangGraph ToolNode",
    )
    memories: MemoryComponents = Field(
        ..., title="Memory Components", description="All agent memory stores grouped together"
    )
    conditional_logic: ConditionalLogic = Field(
        ...,
        title="Conditional Logic",
        description=(
            "Logic instance that determines graph edge routing. Required so "
            "max_debate_rounds / max_risk_discuss_rounds always thread from "
            "TradingAgentsConfig instead of silently defaulting."
        ),
    )

    # --- Private helpers ---

    @staticmethod
    def validate_selected_analysts(selected_analysts: list[str]) -> list[str]:
        """Validate analyst names and normalize duplicate selections."""
        normalized = []
        for analyst in selected_analysts:
            value = analyst.strip().lower()
            if value and value not in normalized:
                normalized.append(value)

        unknown = [analyst for analyst in normalized if analyst not in SUPPORTED_ANALYSTS]
        if unknown:
            raise ValueError(
                "Unknown analyst(s): "
                f"{', '.join(unknown)}. Supported analysts: {', '.join(SUPPORTED_ANALYSTS)}."
            )
        if not normalized:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")
        return normalized

    def _build_analyst_nodes(
        self, selected_analysts: list[str]
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Create analyst, delete and tool nodes for selected analysts.

        Args:
            selected_analysts (list[str]): List of analyst types.

        Returns:
            tuple[dict[str, Any], dict[str, Any], dict[str, Any]]: Analyst
                nodes, message deletion nodes, and tool nodes keyed by analyst type.
        """
        analyst_creators = {
            "market": create_market_analyst,
            "social": create_social_media_analyst,
            "news": create_news_analyst,
            "fundamentals": create_fundamentals_analyst,
        }
        analyst_nodes: dict[str, Any] = {}
        delete_nodes: dict[str, Any] = {}
        tool_nodes: dict[str, Any] = {}

        for analyst_type in selected_analysts:
            if analyst_type in analyst_creators:
                analyst_nodes[analyst_type] = analyst_creators[analyst_type](
                    self.quick_thinking_llm
                )
                delete_nodes[analyst_type] = create_msg_delete()
                tool_nodes[analyst_type] = self.tool_nodes[analyst_type]

        return analyst_nodes, delete_nodes, tool_nodes

    def _add_analyst_edges(self, workflow: StateGraph, selected_analysts: list[str]) -> None:
        """Add conditional edges connecting analysts in sequence.

        Args:
            workflow (StateGraph): The LangGraph workflow to modify.
            selected_analysts (list[str]): List of analyst types.
        """
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i + 1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                # The Situation Summariser distils all four analyst reports
                # into a compact BM25 query before any memory-backed node runs.
                workflow.add_edge(current_clear, "Situation Summariser")

    # --- Public methods ---

    def setup_graph(self, selected_analysts: list[str] | None = None) -> CompiledStateGraph:
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list[str] | None, optional): Analyst types to
                include. Defaults to all supported analysts when None. Options are:
                - "market": Market analyst
                - "social": News sentiment analyst (internal key retained for compatibility)
                - "news": News analyst
                - "fundamentals": Fundamentals analyst

        Returns:
            CompiledStateGraph: The compiled workflow graph.

        Raises:
            ValueError: If no analysts are selected.
        """
        if selected_analysts is None:
            selected_analysts = list(SUPPORTED_ANALYSTS)
        selected_analysts = self.validate_selected_analysts(selected_analysts)

        analyst_nodes, delete_nodes, tool_nodes = self._build_analyst_nodes(selected_analysts)

        # Create situation summariser node (preprocessor between analysts and the research debate)
        situation_summariser_node = create_situation_summariser(self.quick_thinking_llm)

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm, self.memories.bull)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm, self.memories.bear)
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.memories.invest_judge
        )
        trader_node = create_trader(self.quick_thinking_llm, self.memories.trader)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        risk_manager_node = create_risk_manager(self.deep_thinking_llm, self.memories.risk_manager)

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type])
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add other nodes
        workflow.add_node("Situation Summariser", situation_summariser_node)
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Risk Judge", risk_manager_node)

        # Define edges - start with the first analyst
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        # Connect analysts in sequence; the last analyst's Msg Clear feeds the Summariser
        self._add_analyst_edges(workflow, selected_analysts)
        workflow.add_edge("Situation Summariser", "Bull Researcher")

        # Add research team edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bear Researcher": "Bear Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {"Bull Researcher": "Bull Researcher", "Research Manager": "Research Manager"},
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")

        # Add risk management edges
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Conservative Analyst": "Conservative Analyst", "Risk Judge": "Risk Judge"},
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Neutral Analyst": "Neutral Analyst", "Risk Judge": "Risk Judge"},
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {"Aggressive Analyst": "Aggressive Analyst", "Risk Judge": "Risk Judge"},
        )

        workflow.add_edge("Risk Judge", END)

        # Compile and return
        return workflow.compile()
