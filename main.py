import datetime

from tradingagents.default_config import DataVendorsConfig, TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = TradingAgentsConfig(
    llm_provider="google",
    deep_think_llm="gemini-3.1-pro-preview",
    quick_think_llm="gemini-3-flash-preview",
    max_debate_rounds=1,
    data_vendors=DataVendorsConfig(
        core_stock_apis="yfinance",
        technical_indicators="yfinance",
        fundamental_data="yfinance",
        news_data="yfinance",
    ),
)

ta = TradingAgentsGraph(debug=True, config=config)
today = datetime.date.today().strftime("%Y-%m-%d")
_, decision = ta.propagate("PLTR", today)
print(decision)  # noqa: T201
