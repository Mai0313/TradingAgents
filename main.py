import datetime

from rich.console import Console

from tradingagents.config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph

console = Console()


def main() -> None:
    """Main entry point for the TradingAgents CLI.

    Initializes the configuration, builds the TradingAgents graph,
    and runs the process for a test ticker symbol.
    """
    config = TradingAgentsConfig(
        llm_provider="google_genai",
        # This is just for testing, so we use the cheapest model for all roles.
        # In a real application, you might want to use different models for different roles.
        deep_think_llm="gemini-flash-latest",
        quick_think_llm="gemini-flash-latest",
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_recur_limit=30,
        reasoning_effort="high",
        response_language="zh-TW",
    )

    ta = TradingAgentsGraph(debug=True, config=config)
    today = datetime.date.today().strftime("%Y-%m-%d")
    _, decision = ta.propagate("GOOG", today)
    console.print(decision)


if __name__ == "__main__":
    main()
