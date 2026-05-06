import re
import json
from typing import Any
import logging
from pathlib import Path
from functools import cached_property
from collections.abc import Callable

from pydantic import Field, BaseModel, ConfigDict, computed_field, model_validator
from langgraph.prebuilt import ToolNode
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import AnyMessage, HumanMessage, messages_to_dict

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
_SAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_path_component(value: str) -> str:
    """Return a filesystem-safe name for per-ticker result paths."""
    safe = _SAFE_PATH_CHARS.sub("_", value.strip()).strip("._")
    return safe or "unknown"


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
        """Run side effects: register the active config singleton and create dirs.

        Returns:
            TradingAgentsGraph: The validated and setup instance.
        """
        set_config(self.config)
        self.config.data_cache_dir.mkdir(parents=True, exist_ok=True)
        return self

    # --- Derived state (lazily computed from config) ---

    def _create_llm(self, model: str) -> ChatModel:
        """Create a ChatModel instance based on config.

        Args:
            model (str): Model identifier.

        Returns:
            ChatModel: The initialized ChatModel instance.
        """
        return build_chat_model(
            self.config.llm_provider,
            model,
            reasoning_effort=self.config.reasoning_effort,
            callbacks=self.callbacks or None,
        )

    @computed_field
    @cached_property
    def deep_thinking_llm(self) -> ChatModel:
        """Deep thinking LLM instance, derived from config.

        Returns:
            ChatModel: Deep thinking LLM instance.
        """
        return self._create_llm(self.config.deep_think_llm)

    @computed_field
    @cached_property
    def quick_thinking_llm(self) -> ChatModel:
        """Quick thinking LLM instance, derived from config.

        Returns:
            ChatModel: Quick thinking LLM instance.
        """
        return self._create_llm(self.config.quick_think_llm)

    @computed_field
    @cached_property
    def bull_memory(self) -> FinancialSituationMemory:
        """Bull researcher memory instance.

        Returns:
            FinancialSituationMemory: Memory instance for the bull researcher.
        """
        return FinancialSituationMemory("bull_memory")

    @computed_field
    @cached_property
    def bear_memory(self) -> FinancialSituationMemory:
        """Bear researcher memory instance.

        Returns:
            FinancialSituationMemory: Memory instance for the bear researcher.
        """
        return FinancialSituationMemory("bear_memory")

    @computed_field
    @cached_property
    def trader_memory(self) -> FinancialSituationMemory:
        """Trader memory instance.

        Returns:
            FinancialSituationMemory: Memory instance for the trader.
        """
        return FinancialSituationMemory("trader_memory")

    @computed_field
    @cached_property
    def invest_judge_memory(self) -> FinancialSituationMemory:
        """Investment judge memory instance.

        Returns:
            FinancialSituationMemory: Memory instance for the investment judge.
        """
        return FinancialSituationMemory("invest_judge_memory")

    @computed_field
    @cached_property
    def risk_manager_memory(self) -> FinancialSituationMemory:
        """Risk manager memory instance.

        Returns:
            FinancialSituationMemory: Memory instance for the risk manager.
        """
        return FinancialSituationMemory("risk_manager_memory")

    @computed_field
    @cached_property
    def tool_nodes(self) -> dict[str, ToolNode]:
        """Tool nodes for different data sources.

        Returns:
            dict[str, ToolNode]: A dictionary mapping data source names to ToolNodes.
        """
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
        """Compiled LangGraph workflow, derived from config and selected analysts.

        Returns:
            CompiledStateGraph: The compiled state graph workflow.
        """
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
        """Graph propagator for state initialization.

        Returns:
            Propagator: A Propagator instance.
        """
        return Propagator(max_recur_limit=self.config.max_recur_limit)

    @computed_field
    @cached_property
    def reflector(self) -> Reflector:
        """Post-trade reflector for memory updates.

        Returns:
            Reflector: A Reflector instance.
        """
        return Reflector(quick_thinking_llm=self.quick_thinking_llm)

    @computed_field
    @cached_property
    def signal_processor(self) -> SignalProcessor:
        """Signal processor for extracting BUY/SELL/HOLD decisions.

        Returns:
            SignalProcessor: A SignalProcessor instance.
        """
        return SignalProcessor()

    # --- Public methods ---

    def propagate(
        self,
        company_name: str,
        trade_date: str,
        on_message: Callable[[AnyMessage], None] | None = None,
        on_state: Callable[[AgentState], None] | None = None,
    ) -> tuple[AgentState, str]:
        """Run the trading agents graph for a company on a specific date.

        Args:
            company_name (str): Company name or ticker symbol.
            trade_date (str): Trading date in YYYY-MM-DD format.
            on_message (Callable[[AnyMessage], None] | None, optional):
                Callback invoked once per newly-produced message during the
                stream. When provided, takes precedence over the default
                debug print path so callers (CLI, TUI) can route output
                through Rich panels instead of message.pretty_print().
                Defaults to None.
            on_state (Callable[[AgentState], None] | None, optional):
                Callback invoked once per stream chunk with the full
                AgentState snapshot. Used by the Textual TUI to update the
                phase progress sidebar from analyst-report / debate
                fields; the CLI does not need this. Defaults to None.

        Returns:
            tuple[AgentState, str]: The final agent state and the extracted signal decision.

        Raises:
            RuntimeError: If the graph execution produces no output.
        """
        self.ticker = company_name

        init_agent_state = self.propagator.create_initial_state(company_name, trade_date)
        args = self.propagator.get_graph_args(callbacks=self.callbacks or None)

        # Stream in "values" mode (set by Propagator.get_graph_args) so each chunk
        # is the full state snapshot after a node runs. The graph clears
        # state.messages between analysts via Msg Clear nodes, so the only way
        # to capture every round of LLM dialogue is to collect messages as they
        # appear in stream chunks (deduped by id).
        raw_state = None
        last_emitted_id = None
        collected: dict[str, AnyMessage] = {}
        for chunk in self.graph.stream(init_agent_state, **args):
            last_emitted_id = self._dispatch_messages(
                chunk, collected, last_emitted_id, on_message
            )
            if on_state is not None:
                self._dispatch_state(chunk, on_state)
            raw_state = chunk

        if raw_state is None:
            raise RuntimeError("Graph produced no output")

        final_state = (
            AgentState.model_validate(raw_state) if isinstance(raw_state, dict) else raw_state
        )

        self.curr_state = final_state
        self._log_state(trade_date, final_state, list(collected.values()))
        return final_state, self.process_signal(final_state.final_trade_decision)

    def _dispatch_messages(
        self,
        chunk: Any,  # noqa: ANN401  # langgraph stream chunk is dict|AgentState|None
        collected: dict[str, AnyMessage],
        last_emitted_id: str | None,
        on_message: Callable[[AnyMessage], None] | None,
    ) -> str | None:
        """Forward newly-arrived messages from one stream chunk.

        Mutates ``collected`` so the eventual ``_log_state`` call sees
        every message that ever flew past, even those wiped by Msg
        Clear nodes between analyst phases.

        Args:
            chunk (Any): One snapshot from ``graph.stream`` -- either a
                dict (the common case) or an AgentState-like object.
            collected (dict[str, AnyMessage]): Per-run accumulator
                mapping message ID to message; updated in-place.
            last_emitted_id (str | None): The ID of the last message
                already forwarded to ``on_message`` / pretty_print.
            on_message (Callable[[AnyMessage], None] | None): External
                renderer callback. When None, falls back to
                ``message.pretty_print`` if ``self.debug`` is set.

        Returns:
            str | None: The new ``last_emitted_id`` after this chunk.
        """
        messages = (
            chunk.get("messages") if isinstance(chunk, dict) else getattr(chunk, "messages", None)
        )
        if not messages:
            return last_emitted_id
        for msg in messages:
            mid = getattr(msg, "id", None)
            if mid and mid not in collected:
                collected[mid] = msg
        latest = messages[-1]
        if latest.id == last_emitted_id:
            return last_emitted_id
        if on_message is not None:
            on_message(latest)
        elif self.debug:
            latest.pretty_print()
        return latest.id

    def _dispatch_state(
        self,
        chunk: Any,  # noqa: ANN401  # langgraph stream chunk is dict|AgentState
        on_state: Callable[[AgentState], None],
    ) -> None:
        """Validate ``chunk`` as :class:`AgentState` and invoke ``on_state``.

        The TUI's phase sidebar is a best-effort observer, so any
        validation or callback failure is logged at debug level and
        swallowed -- a broken hook must never abort a paid LLM run.

        Args:
            chunk (Any): One stream-chunk snapshot.
            on_state (Callable[[AgentState], None]): Caller-provided
                state observer.
        """
        try:
            snapshot = AgentState.model_validate(chunk) if isinstance(chunk, dict) else chunk
            on_state(snapshot)
        except Exception:
            logger.debug("on_state hook failed", exc_info=True)

    def _log_state(
        self, trade_date: str, final_state: AgentState, all_messages: list[AnyMessage]
    ) -> None:
        """Log final state and conversation history for a graph run.

        Args:
            trade_date (str): Trade date in YYYY-MM-DD format.
            final_state (AgentState): The final agent state to log.
            all_messages (list[AnyMessage]): Every message observed across the
                graph run, in arrival order. Required because per-analyst Msg
                Clear nodes wipe ``final_state.messages`` between rounds.
        """
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

        ticker_name = _safe_path_component(self.ticker or "unknown")
        directory = self.config.results_dir / ticker_name
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{ticker_name}_{trade_date}.json"
        with open(log_path, "w") as f:
            json.dump(self.log_states_dict, f, indent=2, ensure_ascii=False)

        # Save complete conversation log (includes raw tool results: stock data,
        # indicators, news, financials, insider transactions, etc.)
        self._save_conversation_log(
            directory=directory,
            ticker_name=ticker_name,
            trade_date=trade_date,
            messages=all_messages,
        )

    def _save_conversation_log(
        self, directory: Path, ticker_name: str, trade_date: str, messages: list[AnyMessage]
    ) -> None:
        """Save text and JSON conversation logs including raw tool call results.

        Args:
            directory (Path): Output directory path.
            ticker_name (str): Ticker symbol for naming the log files.
            trade_date (str): Trade date.
            messages (list[AnyMessage]): Full conversation collected across the graph run.
        """
        # Drop the "Continue" placeholders injected by Msg Clear nodes — they
        # are graph plumbing for Anthropic's message-ordering rules, not real
        # conversation turns.
        filtered = [
            msg
            for msg in messages
            if not (isinstance(msg, HumanMessage) and msg.content == "Continue")
        ]

        # Human-readable text log (same format as debug pretty_print output)
        txt_path = directory / f"conversation_log_{ticker_name}_{trade_date}.txt"
        try:
            with open(txt_path, "w") as f:
                for msg in filtered:
                    f.write(msg.pretty_repr() + "\n")
            logger.info("Conversation log saved to %s", txt_path)
        except Exception:
            logger.warning("Failed to save conversation text log", exc_info=True)

        # Structured JSON log (machine-readable, for programmatic analysis)
        json_path = directory / f"conversation_log_{ticker_name}_{trade_date}.json"
        try:
            with open(json_path, "w") as f:
                json.dump(messages_to_dict(filtered), f, indent=2, ensure_ascii=False)
            logger.info("Conversation JSON saved to %s", json_path)
        except Exception:
            logger.warning("Failed to save conversation JSON log", exc_info=True)

    def reflect_and_remember(self, returns_losses: float) -> None:
        """Reflect on decisions and update memory based on returns.

        Args:
            returns_losses (float): Actual returns or losses from the trade.

        Raises:
            RuntimeError: If there is no current state to reflect on.
        """
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
        """Process a signal to extract the core decision.

        Args:
            full_signal (str): The raw text signal.

        Returns:
            str: The extracted decision (BUY/SELL/HOLD).
        """
        return self.signal_processor.process_signal(full_signal)
