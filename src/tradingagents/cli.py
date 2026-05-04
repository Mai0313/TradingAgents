import datetime

from tradingagents.config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph


def main() -> None:
    """Main entry point for the TradingAgents CLI.

    Initializes the configuration, builds the TradingAgents graph,
    and runs the process for a test ticker symbol.
    """
    config = TradingAgentsConfig(
        llm_provider="google_genai",
        deep_think_llm="gemini-3.1-pro-preview",
        quick_think_llm="gemini-3-flash-preview",
        max_debate_rounds=10,
        max_risk_discuss_rounds=10,
        max_recur_limit=100,
        reasoning_effort="high",
        response_language="zh-TW",
    )

    ta = TradingAgentsGraph(debug=True, config=config)
    today = datetime.date.today().strftime("%Y-%m-%d")
    _, decision = ta.propagate("GOOG", today)
    print(decision)  # noqa: T201


if __name__ == "__main__":
    main()
