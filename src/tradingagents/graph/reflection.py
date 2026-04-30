# TradingAgents/graph/reflection.py

from pydantic import Field, BaseModel, ConfigDict, SkipValidation

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import AgentState


class Reflector(BaseModel):
    """Handles reflection on decisions and updating memory."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # --- User-configurable fields ---

    quick_thinking_llm: SkipValidation[ChatModel] = Field(
        ...,
        title="Quick Thinking LLM",
        description="LLM instance used for generating reflection analysis",
    )

    # --- Private helpers ---

    def _extract_current_situation(self, current_state: AgentState) -> str:
        """Extract the current market situation from the state."""
        return (
            f"{current_state.market_report}\n\n"
            f"{current_state.sentiment_report}\n\n"
            f"{current_state.news_report}\n\n"
            f"{current_state.fundamentals_report}"
        )

    def _reflect_on_component(
        self, component_type: str, report: str, situation: str, returns_losses: float
    ) -> str:
        """Generate reflection for a component."""
        messages = [
            ("system", load_prompt("reflector")),
            (
                "human",
                f"Returns: {returns_losses}\n\nAnalysis/Decision: {report}\n\nObjective Market Reports for Reference: {situation}",
            ),
        ]

        result = self.quick_thinking_llm.invoke(messages).content
        return result

    # --- Public methods ---

    def reflect_bull_researcher(
        self,
        current_state: AgentState,
        returns_losses: float,
        bull_memory: FinancialSituationMemory,
    ) -> None:
        """Reflect on bull researcher's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        result = self._reflect_on_component(
            "BULL", current_state.investment_debate_state.bull_history, situation, returns_losses
        )
        bull_memory.add_situations([(situation, result)])

    def reflect_bear_researcher(
        self,
        current_state: AgentState,
        returns_losses: float,
        bear_memory: FinancialSituationMemory,
    ) -> None:
        """Reflect on bear researcher's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        result = self._reflect_on_component(
            "BEAR", current_state.investment_debate_state.bear_history, situation, returns_losses
        )
        bear_memory.add_situations([(situation, result)])

    def reflect_trader(
        self,
        current_state: AgentState,
        returns_losses: float,
        trader_memory: FinancialSituationMemory,
    ) -> None:
        """Reflect on trader's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        result = self._reflect_on_component(
            "TRADER", current_state.trader_investment_plan, situation, returns_losses
        )
        trader_memory.add_situations([(situation, result)])

    def reflect_invest_judge(
        self,
        current_state: AgentState,
        returns_losses: float,
        invest_judge_memory: FinancialSituationMemory,
    ) -> None:
        """Reflect on investment judge's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        result = self._reflect_on_component(
            "INVEST JUDGE",
            current_state.investment_debate_state.judge_decision,
            situation,
            returns_losses,
        )
        invest_judge_memory.add_situations([(situation, result)])

    def reflect_risk_manager(
        self,
        current_state: AgentState,
        returns_losses: float,
        risk_manager_memory: FinancialSituationMemory,
    ) -> None:
        """Reflect on risk manager's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        result = self._reflect_on_component(
            "RISK JUDGE", current_state.risk_debate_state.judge_decision, situation, returns_losses
        )
        risk_manager_memory.add_situations([(situation, result)])
