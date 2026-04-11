import datetime

from tradingagents.default_config import LLMProvider, TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = TradingAgentsConfig(
    llm_provider=LLMProvider.GOOGLE,
    deep_think_llm="gemini-3.1-pro-preview",
    quick_think_llm="gemini-3-flash-preview",
    max_debate_rounds=1,
    max_risk_discuss_rounds=1,
    max_recur_limit=100,
    reasoning_effort="high"
)

ta = TradingAgentsGraph(debug=True, config=config)
today = datetime.date.today().strftime("%Y-%m-%d")
_, decision = ta.propagate("PLTR", today)
print(decision)  # noqa: T201
