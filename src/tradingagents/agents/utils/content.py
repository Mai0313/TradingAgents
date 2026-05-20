"""Shared helpers for provider-specific LangChain message content shapes."""

from typing import Any


def flatten_message_content(content: object) -> str:
    """Flatten a LangChain ``message.content`` payload into plain text.

    Some providers return list-shaped content chunks such as
    ``{"type": "text", "text": "..."}``; every downstream state field
    stores strings, so node code should normalize through this helper before
    concatenating or persisting model output.
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
    return str(content or "")


def has_tool_evidence(messages: list[Any]) -> bool:
    """Return whether the current analyst loop has observed any tool result."""
    for message in messages:
        if getattr(message, "type", None) == "tool":
            return True
        if message.__class__.__name__ == "ToolMessage":
            return True
    return False


def analyst_report_or_evidence_warning(  # noqa: PLR0913
    *,
    analyst_name: str,
    ticker: str,
    trade_date: str,
    messages: list[Any],
    tool_calls: object,
    content: object,
) -> str:
    """Return an analyst report or a warning when no tool evidence exists."""
    if tool_calls:
        return ""

    report = flatten_message_content(content)
    if has_tool_evidence(messages):
        return report

    return (
        f"[TOOL_ERROR] {analyst_name} produced a final report before any tool "
        f"result was observed for {ticker} as of {trade_date}. This analyst "
        "section is intentionally marked unavailable because the report was "
        "not grounded in reproducible tool evidence."
    )
