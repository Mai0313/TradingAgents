# TradingAgents/graph/setup.py

from typing import Any
from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.graph.state import CompiledStateGraph
from langchain_core.language_models import BaseChatModel

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
    create_social_media_analyst,
)
from tradingagents.agents.utils.memory import FinancialSituationMemory

from .conditional_logic import ConditionalLogic


@dataclass
class MemoryComponents:
    """Groups all memory components for the trading agents."""

    bull: FinancialSituationMemory
    bear: FinancialSituationMemory
    trader: FinancialSituationMemory
    invest_judge: FinancialSituationMemory
    risk_manager: FinancialSituationMemory


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: BaseChatModel,
        deep_thinking_llm: BaseChatModel,
        tool_nodes: dict[str, ToolNode],
        memories: MemoryComponents,
        conditional_logic: ConditionalLogic,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = memories.bull
        self.bear_memory = memories.bear
        self.trader_memory = memories.trader
        self.invest_judge_memory = memories.invest_judge
        self.risk_manager_memory = memories.risk_manager
        self.conditional_logic = conditional_logic

    def _build_analyst_nodes(
        self, selected_analysts: list[str]
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Create analyst, delete and tool nodes for selected analysts."""
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
        """Add conditional edges connecting analysts in sequence."""
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
                workflow.add_edge(current_clear, "Bull Researcher")

    def setup_graph(self, selected_analysts: list[str] | None = None) -> CompiledStateGraph:
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts: List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
        """
        if selected_analysts is None:
            selected_analysts = ["market", "social", "news", "fundamentals"]
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        analyst_nodes, delete_nodes, tool_nodes = self._build_analyst_nodes(selected_analysts)

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm, self.bull_memory)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm, self.bear_memory)
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        risk_manager_node = create_risk_manager(self.deep_thinking_llm, self.risk_manager_memory)

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type])
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add other nodes
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

        # Connect analysts in sequence
        self._add_analyst_edges(workflow, selected_analysts)

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
