# TradingAgents/graph/trading_graph.py

import json
from typing import Any
import logging
from pathlib import Path
from functools import cached_property

from pydantic import Field, BaseModel, ConfigDict, computed_field, model_validator
from langgraph.prebuilt import ToolNode
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import messages_to_dict

from tradingagents.llm import ChatModel, build_chat_model
from tradingagents.config import TradingAgentsConfig, set_config
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_utils import (
    get_news,
    get_cashflow,
    get_indicators,
    get_stock_data,
    get_global_news,
    get_fundamentals,
    get_balance_sheet,
    get_income_statement,
    get_insider_transactions,
)
from tradingagents.agents.utils.agent_states import AgentState

from .setup import GraphSetup, MemoryComponents
from .reflection import Reflector
from .propagation import Propagator
from .conditional_logic import ConditionalLogic
from .signal_processing import SignalProcessor

logger = logging.getLogger(__name__)


class TradingAgentsGraph(BaseModel):
    """Main class that orchestrates the trading agents framework."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # --- User-configurable fields ---
    selected_analysts: list[str] = Field(
        default=["market", "social", "news", "fundamentals"],
        title="Selected Analysts",
        description="List of analyst types to include in the trading graph",
    )
    debug: bool = Field(
        default=False,
        title="Debug Mode",
        description="Enable debug mode with step-by-step tracing output",
    )
    config: TradingAgentsConfig = Field(
        ..., title="Configuration", description="Trading agents configuration settings"
    )
    callbacks: list = Field(
        default_factory=list,
        title="Callbacks",
        description="Optional callback handlers for tracking LLM/tool statistics",
    )

    # --- Mutable runtime state (updated by propagate() etc.) ---
    curr_state: AgentState | None = Field(
        default=None,
        title="Current State",
        description="Current graph execution state, populated after propagate()",
    )
    ticker: str = Field(
        default="", title="Ticker", description="Current stock ticker symbol being analyzed"
    )
    log_states_dict: dict[str, Any] = Field(
        default_factory=dict,
        title="Log States",
        description="Accumulated state logs keyed by trade date",
    )

    @model_validator(mode="after")
    def _setup(self) -> "TradingAgentsGraph":
        """Run side effects: register the active config singleton and create dirs."""
        set_config(self.config)
        self.config.data_cache_dir.mkdir(parents=True, exist_ok=True)
        return self

    # --- Derived state (lazily computed from config) ---

    def _create_llm(self, model: str) -> ChatModel:
        return build_chat_model(
            self.config.llm_provider,
            model,
            reasoning_effort=self.config.reasoning_effort,
            callbacks=self.callbacks or None,
        )

    @computed_field
    @cached_property
    def deep_thinking_llm(self) -> ChatModel:
        """Deep thinking LLM instance, derived from config."""
        return self._create_llm(self.config.deep_think_llm)

    @computed_field
    @cached_property
    def quick_thinking_llm(self) -> ChatModel:
        """Quick thinking LLM instance, derived from config."""
        return self._create_llm(self.config.quick_think_llm)

    @computed_field
    @cached_property
    def bull_memory(self) -> FinancialSituationMemory:
        """Bull researcher memory instance."""
        return FinancialSituationMemory("bull_memory")

    @computed_field
    @cached_property
    def bear_memory(self) -> FinancialSituationMemory:
        """Bear researcher memory instance."""
        return FinancialSituationMemory("bear_memory")

    @computed_field
    @cached_property
    def trader_memory(self) -> FinancialSituationMemory:
        """Trader memory instance."""
        return FinancialSituationMemory("trader_memory")

    @computed_field
    @cached_property
    def invest_judge_memory(self) -> FinancialSituationMemory:
        """Investment judge memory instance."""
        return FinancialSituationMemory("invest_judge_memory")

    @computed_field
    @cached_property
    def risk_manager_memory(self) -> FinancialSituationMemory:
        """Risk manager memory instance."""
        return FinancialSituationMemory("risk_manager_memory")

    @computed_field
    @cached_property
    def tool_nodes(self) -> dict[str, ToolNode]:
        """Tool nodes for different data sources."""
        return {
            "market": ToolNode([get_stock_data, get_indicators]),
            "social": ToolNode([get_news]),
            "news": ToolNode([get_news, get_global_news, get_insider_transactions]),
            "fundamentals": ToolNode([
                get_fundamentals,
                get_balance_sheet,
                get_cashflow,
                get_income_statement,
            ]),
        }

    @computed_field
    @cached_property
    def graph(self) -> CompiledStateGraph:
        """Compiled LangGraph workflow, derived from config and selected analysts."""
        memories = MemoryComponents(
            bull=self.bull_memory,
            bear=self.bear_memory,
            trader=self.trader_memory,
            invest_judge=self.invest_judge_memory,
            risk_manager=self.risk_manager_memory,
        )
        graph_setup = GraphSetup(
            quick_thinking_llm=self.quick_thinking_llm,
            deep_thinking_llm=self.deep_thinking_llm,
            tool_nodes=self.tool_nodes,
            memories=memories,
            conditional_logic=ConditionalLogic(
                max_debate_rounds=self.config.max_debate_rounds,
                max_risk_discuss_rounds=self.config.max_risk_discuss_rounds,
            ),
        )
        return graph_setup.setup_graph(self.selected_analysts)

    @computed_field
    @cached_property
    def propagator(self) -> Propagator:
        """Graph propagator for state initialization."""
        return Propagator(max_recur_limit=self.config.max_recur_limit)

    @computed_field
    @cached_property
    def reflector(self) -> Reflector:
        """Post-trade reflector for memory updates."""
        return Reflector(quick_thinking_llm=self.quick_thinking_llm)

    @computed_field
    @cached_property
    def signal_processor(self) -> SignalProcessor:
        """Signal processor for extracting BUY/SELL/HOLD decisions."""
        return SignalProcessor(quick_thinking_llm=self.quick_thinking_llm)

    # --- Public methods ---

    def propagate(self, company_name: str, trade_date: str) -> tuple[AgentState, str]:
        """Run the trading agents graph for a company on a specific date."""
        self.ticker = company_name

        init_agent_state = self.propagator.create_initial_state(company_name, trade_date)
        args = self.propagator.get_graph_args(callbacks=self.callbacks or None)

        if self.debug:
            raw_state = None
            last_printed_id = None
            for chunk in self.graph.stream(init_agent_state, **args):
                messages = (
                    chunk.get("messages")
                    if isinstance(chunk, dict)
                    else getattr(chunk, "messages", None)
                )
                if messages and messages[-1].id != last_printed_id:
                    messages[-1].pretty_print()
                    last_printed_id = messages[-1].id
                raw_state = chunk
        else:
            raw_state = self.graph.invoke(init_agent_state, **args)

        if raw_state is None:
            raise RuntimeError("Graph produced no output")

        final_state = (
            AgentState.model_validate(raw_state) if isinstance(raw_state, dict) else raw_state
        )

        self.curr_state = final_state
        self._log_state(trade_date, final_state)
        return final_state, self.process_signal(final_state.final_trade_decision)

    def _log_state(self, trade_date: str, final_state: AgentState) -> None:
        """Log the final state to a JSON file."""
        invest = final_state.investment_debate_state
        risk = final_state.risk_debate_state
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state.company_of_interest,
            "trade_date": final_state.trade_date,
            "market_report": final_state.market_report,
            "sentiment_report": final_state.sentiment_report,
            "news_report": final_state.news_report,
            "fundamentals_report": final_state.fundamentals_report,
            "investment_debate_state": {
                "bull_history": invest.bull_history,
                "bear_history": invest.bear_history,
                "history": invest.history,
                "current_response": invest.current_response,
                "judge_decision": invest.judge_decision,
            },
            "trader_investment_decision": final_state.trader_investment_plan,
            "risk_debate_state": {
                "aggressive_history": risk.aggressive_history,
                "conservative_history": risk.conservative_history,
                "neutral_history": risk.neutral_history,
                "history": risk.history,
                "judge_decision": risk.judge_decision,
            },
            "investment_plan": final_state.investment_plan,
            "final_trade_decision": final_state.final_trade_decision,
        }

        ticker_name = self.ticker or "unknown"
        directory = self.config.results_dir / ticker_name / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w") as f:
            json.dump(self.log_states_dict, f, indent=2, ensure_ascii=False)

        # Save complete conversation log (includes raw tool results: stock data,
        # indicators, news, financials, insider transactions, etc.)
        self._save_conversation_log(directory, trade_date, final_state)

    def _save_conversation_log(
        self, directory: Path, trade_date: str, final_state: AgentState
    ) -> None:
        """Save the full conversation history including raw tool call results."""
        # Human-readable text log (same format as debug pretty_print output)
        txt_path = directory / f"conversation_log_{trade_date}.txt"
        try:
            with open(txt_path, "w") as f:
                for msg in final_state.messages:
                    f.write(msg.pretty_repr() + "\n")
            logger.info("Conversation log saved to %s", txt_path)
        except Exception:
            logger.warning("Failed to save conversation text log", exc_info=True)

        # Structured JSON log (machine-readable, for programmatic analysis)
        json_path = directory / f"conversation_log_{trade_date}.json"
        try:
            with open(json_path, "w") as f:
                json.dump(messages_to_dict(final_state.messages), f, indent=2, ensure_ascii=False)
            logger.info("Conversation JSON saved to %s", json_path)
        except Exception:
            logger.warning("Failed to save conversation JSON log", exc_info=True)

    def reflect_and_remember(self, returns_losses: float) -> None:
        """Reflect on decisions and update memory based on returns."""
        if self.curr_state is None:
            raise RuntimeError("No state available to reflect on. Run propagate() first.")
        self.reflector.reflect_bull_researcher(self.curr_state, returns_losses, self.bull_memory)
        self.reflector.reflect_bear_researcher(self.curr_state, returns_losses, self.bear_memory)
        self.reflector.reflect_trader(self.curr_state, returns_losses, self.trader_memory)
        self.reflector.reflect_invest_judge(
            self.curr_state, returns_losses, self.invest_judge_memory
        )
        self.reflector.reflect_risk_manager(
            self.curr_state, returns_losses, self.risk_manager_memory
        )

    def process_signal(self, full_signal: str) -> str:
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)
