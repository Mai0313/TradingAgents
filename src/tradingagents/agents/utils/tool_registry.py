"""Central registry for analyst tool ownership.

The graph ToolNodes, analyst LLM ``bind_tools(...)`` calls, and prompt
``tool_names`` partials must all agree on the same tool set. Keeping the
mapping here prevents prompt / graph / node drift.
"""

from typing import Literal

from langchain_core.tools import BaseTool

from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_global_news,
    get_market_context,
    get_earnings_calendar,
    get_insider_transactions,
)
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fundamental_data_tools import (
    get_cashflow,
    get_fundamentals,
    get_balance_sheet,
    get_short_interest,
    get_analyst_ratings,
    get_dividends_splits,
    get_income_statement,
    get_institutional_holders,
)
from tradingagents.agents.utils.technical_indicators_tools import get_indicators

AnalystType = Literal["market", "social", "news", "fundamentals"]

ANALYST_TOOL_REGISTRY: dict[AnalystType, tuple[BaseTool, ...]] = {
    "market": (get_stock_data, get_indicators, get_dividends_splits),
    "social": (get_news,),
    "news": (
        get_news,
        get_global_news,
        get_insider_transactions,
        get_market_context,
        get_earnings_calendar,
    ),
    "fundamentals": (
        get_fundamentals,
        get_balance_sheet,
        get_cashflow,
        get_income_statement,
        get_analyst_ratings,
        get_institutional_holders,
        get_short_interest,
        get_dividends_splits,
    ),
}


def get_analyst_tools(analyst_type: AnalystType) -> tuple[BaseTool, ...]:
    """Return the registered tool tuple for ``analyst_type``."""
    return ANALYST_TOOL_REGISTRY[analyst_type]


def get_analyst_tool_names(analyst_type: AnalystType) -> str:
    """Return a comma-separated tool-name string for prompt partials."""
    return ", ".join(tool.name for tool in get_analyst_tools(analyst_type))
