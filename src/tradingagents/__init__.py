"""TradingAgents: Multi-Agents LLM Financial Trading Framework.

Top-level public API. Kept intentionally small: importing this package
should not pull in the CLI / TUI dependency tree (fire, questionary,
rich). Those live under :mod:`tradingagents.interface`.
"""

from tradingagents.config import TradingAgentsConfig, get_config, set_config
from tradingagents.graph.trading_graph import TradingAgentsGraph

__all__ = ["TradingAgentsConfig", "TradingAgentsGraph", "get_config", "set_config"]
