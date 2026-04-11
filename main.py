import datetime

from tradingagents.default_config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = TradingAgentsConfig(
    llm_provider="google",
    deep_think_llm="gemini-3-flash-preview",
    quick_think_llm="gemini-3-flash-preview",
    max_debate_rounds=1,
)

ta = TradingAgentsGraph(debug=True, config=config)
today = datetime.date.today().strftime("%Y-%m-%d")
_, decision = ta.propagate("PLTR", today)
print(decision)  # noqa: T201
