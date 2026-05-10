# TradingAgents/graph/reflection.py

from pydantic import Field, BaseModel, ConfigDict, SkipValidation
from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.llm import ChatModel
from tradingagents.agents.prompts import load_prompt
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import AgentState


def _flatten_content(content: object) -> str:
    """Flatten a LangChain message ``.content`` value to a string.

    Anthropic Claude and Gemini 3 sometimes return list-shaped content
    (a list of ``{"type": "text", "text": "..."}`` chunks); BM25 then
    fails because ``"".lower()`` is not defined for lists. This
    normaliser is a single source of truth for that flattening.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


class Reflector(BaseModel):
    """Generates per-agent reflections used to update the BM25 memories."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    quick_thinking_llm: SkipValidation[ChatModel] = Field(
        ...,
        title="Quick Thinking LLM",
        description="LLM instance used for generating reflection analysis",
    )

    def _reflect_on_component(self, report: str, situation: str, returns_losses: float) -> str:
        """Generate a reflection paragraph for a single decision component.

        Args:
            report: The component's history / report / plan to reflect on.
            situation: The combined market situation snapshot.
            returns_losses: Realised P/L for the trade.

        Returns:
            The reflector LLM's text response, flattened to a plain string.
        """
        messages = [
            SystemMessage(content=load_prompt("reflector")),
            HumanMessage(
                content=(
                    f"Returns: {returns_losses}\n\n"
                    f"Analysis/Decision: {report}\n\n"
                    f"Objective Market Reports for Reference: {situation}"
                )
            ),
        ]
        return _flatten_content(self.quick_thinking_llm.invoke(messages).content)

    def reflect_bull_researcher(
        self,
        current_state: AgentState,
        returns_losses: float,
        bull_memory: FinancialSituationMemory,
    ) -> None:
        """Reflect on the bull researcher's history and update its memory."""
        situation = current_state.combined_reports
        result = self._reflect_on_component(
            current_state.investment_debate_state.bull_history, situation, returns_losses
        )
        bull_memory.add_situations([(situation, result)])

    def reflect_bear_researcher(
        self,
        current_state: AgentState,
        returns_losses: float,
        bear_memory: FinancialSituationMemory,
    ) -> None:
        """Reflect on the bear researcher's history and update its memory."""
        situation = current_state.combined_reports
        result = self._reflect_on_component(
            current_state.investment_debate_state.bear_history, situation, returns_losses
        )
        bear_memory.add_situations([(situation, result)])

    def reflect_trader(
        self,
        current_state: AgentState,
        returns_losses: float,
        trader_memory: FinancialSituationMemory,
    ) -> None:
        """Reflect on the trader's plan and update its memory."""
        situation = current_state.combined_reports
        result = self._reflect_on_component(
            current_state.trader_investment_plan, situation, returns_losses
        )
        trader_memory.add_situations([(situation, result)])

    def reflect_invest_judge(
        self,
        current_state: AgentState,
        returns_losses: float,
        invest_judge_memory: FinancialSituationMemory,
    ) -> None:
        """Reflect on the research-manager verdict and update its memory."""
        situation = current_state.combined_reports
        result = self._reflect_on_component(
            current_state.investment_debate_state.judge_decision, situation, returns_losses
        )
        invest_judge_memory.add_situations([(situation, result)])

    def reflect_risk_manager(
        self,
        current_state: AgentState,
        returns_losses: float,
        risk_manager_memory: FinancialSituationMemory,
    ) -> None:
        """Reflect on the risk-manager verdict and update its memory."""
        situation = current_state.combined_reports
        result = self._reflect_on_component(
            current_state.risk_debate_state.judge_decision, situation, returns_losses
        )
        risk_manager_memory.add_situations([(situation, result)])
