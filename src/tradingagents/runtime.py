"""Per-run execution context shared by graph nodes and tools."""

from datetime import date
from contextvars import Token, ContextVar

from pydantic import Field, BaseModel, field_validator

from tradingagents.config import ResponseLanguage

_TOOL_ERROR_PREFIX = "[TOOL_ERROR]"


class RunContext(BaseModel):
    """Point-in-time context for one ``TradingAgentsGraph.propagate`` run."""

    ticker: str = Field(
        ...,
        title="Ticker",
        description="Ticker or company symbol being analysed in the active graph run.",
    )
    trade_date: date = Field(
        ..., title="Trade Date", description="As-of date that every tool call must respect."
    )
    response_language: ResponseLanguage = Field(
        ...,
        title="Response Language",
        description="BCP 47 response-language tag from the active TradingAgentsConfig.",
    )

    @field_validator("ticker")
    @classmethod
    def _ticker_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("ticker cannot be blank.")
        return cleaned


_active_run_context: ContextVar[RunContext | None] = ContextVar(
    "tradingagents_active_run_context", default=None
)


def set_run_context(context: RunContext) -> Token[RunContext | None]:
    """Register ``context`` for the current execution context."""
    return _active_run_context.set(context)


def reset_run_context(token: Token[RunContext | None]) -> None:
    """Restore the previous run context from ``token``."""
    _active_run_context.reset(token)


def get_run_context() -> RunContext | None:
    """Return the active run context, or None outside graph execution."""
    return _active_run_context.get()


def _parse_date(value: str) -> date | None:
    """Parse YYYY-MM-DD, returning None so the dataflow can own format errors."""
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def reject_future_tool_dates(tool_name: str, **date_args: str | None) -> str | None:
    """Return a ``[TOOL_ERROR]`` if any supplied tool date exceeds trade_date.

    The guard is intentionally strict: future requests are rejected rather
    than clamped so prompt / caller bugs are visible in logs and analyst
    reports.
    """
    context = get_run_context()
    if context is None:
        return None

    for field_name, raw_value in date_args.items():
        if raw_value is None:
            continue
        parsed = _parse_date(raw_value)
        if parsed is None:
            continue
        if parsed > context.trade_date:
            return (
                f"{_TOOL_ERROR_PREFIX} {tool_name} refused future {field_name}={raw_value} "
                f"because active trade_date is {context.trade_date.isoformat()} "
                f"for ticker {context.ticker}. Fix the tool arguments instead of "
                "reading or silently clamping future data."
            )
    return None
