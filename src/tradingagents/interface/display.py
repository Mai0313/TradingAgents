"""Rich-based display utilities shared by the CLI, the TUI, and the graph runtime.

This module owns the single :class:`rich.console.Console` instance used across
the project and provides a Rich replacement for
:meth:`langchain_core.messages.BaseMessage.pretty_print`. The replacement is
intentionally a free function (rather than a monkey-patch on ``BaseMessage``)
so callers that import LangChain elsewhere keep the original behaviour.
"""

from typing import Any

from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.console import Group, Console
from rich.markdown import Markdown
from langchain_core.messages import BaseMessage

console: Console = Console()
"""Project-wide Rich console; reuse this instead of constructing new ones."""

_ROLE_STYLES: dict[str, tuple[str, str]] = {
    "human": ("Human", "cyan"),
    "ai": ("AI", "magenta"),
    "tool": ("Tool", "green"),
    "system": ("System", "yellow"),
    "function": ("Function", "blue"),
}


def _format_tool_calls(tool_calls: list[dict[str, Any]]) -> Table:
    """Render LangChain tool calls as a Rich table.

    Args:
        tool_calls (list[dict[str, Any]]): Tool calls attached to an
            ``AIMessage``. Each entry is expected to contain ``name``, ``args``,
            and ``id`` keys.

    Returns:
        Table: A formatted Rich table summarising the tool invocations.
    """
    table = Table(title="Tool Calls", show_header=True, header_style="bold green", expand=True)
    table.add_column("Name", style="bold green", no_wrap=True)
    table.add_column("Args", overflow="fold")
    table.add_column("Call ID", style="dim", no_wrap=True)
    for tc in tool_calls:
        args = tc.get("args", {})
        args_repr = (
            ", ".join(f"{k}={v!r}" for k, v in args.items())
            if isinstance(args, dict)
            else str(args)
        )
        table.add_row(str(tc.get("name", "")), args_repr or "-", str(tc.get("id", "")))
    return table


def _content_to_str(content: str | list[str | dict[str, Any]]) -> str:
    """Flatten a LangChain message ``content`` field to a plain string.

    Some providers (e.g. Gemini 3) return a list of content blocks; this helper
    joins them into a single string so the panel body stays readable.

    Args:
        content (str | list[str | dict[str, Any]]): The raw
            ``BaseMessage.content`` value, matching LangChain's union type.

    Returns:
        str: A plain-text representation suitable for rendering.
    """
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        else:
            parts.append(str(item))
    return "\n".join(parts).strip()


def pretty_print_message(msg: BaseMessage) -> None:
    """Print a LangChain ``BaseMessage`` as a Rich panel.

    This is a drop-in replacement for ``BaseMessage.pretty_print()`` that
    renders AI content as Markdown, tool calls as a table, and uses
    role-coloured borders. ``ToolMessage`` content is treated as plain text to
    avoid mangling raw tool output (JSON, CSV, etc.).

    Args:
        msg (BaseMessage): The LangChain message to render.
    """
    role_label, color = _ROLE_STYLES.get(msg.type, (msg.type.title(), "white"))
    title = f"[bold {color}]{role_label} Message[/bold {color}]"
    if msg.name:
        title += f" [dim]· {msg.name}[/dim]"

    body: list[Any] = []
    text = _content_to_str(msg.content)
    if text:
        body.append(Markdown(text) if msg.type == "ai" else Text(text))

    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        body.append(_format_tool_calls(tool_calls))

    if not body:
        body.append(Text("(empty)", style="dim italic"))

    renderable = body[0] if len(body) == 1 else Group(*body)
    console.print(Panel(renderable, title=title, border_style=color, padding=(1, 2), expand=True))


def print_header(title: str, subtitle: str | None = None) -> None:
    """Print a top-level banner panel.

    Args:
        title (str): Bold title text.
        subtitle (str | None, optional): Dim subtitle rendered below the title.
            Defaults to None.
    """
    body: Any
    if subtitle:
        body = Group(Text(title, style="bold white"), Text(subtitle, style="dim italic"))
    else:
        body = Text(title, style="bold white")
    console.print(Panel(body, border_style="bright_blue", padding=(1, 2), expand=True))


def print_summary(rows: list[tuple[str, str]], title: str = "Configuration") -> None:
    """Print a key/value summary table.

    Args:
        rows (list[tuple[str, str]]): ``(field, value)`` pairs to display.
        title (str, optional): Table title. Defaults to ``"Configuration"``.
    """
    table = Table(title=title, show_header=False, expand=True, padding=(0, 1))
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value", style="white", overflow="fold")
    for k, v in rows:
        table.add_row(k, v)
    console.print(table)


def print_decision(ticker: str, trade_date: str, decision: str) -> None:
    """Print the final BUY/SELL/HOLD decision panel.

    Args:
        ticker (str): The stock ticker that was analysed.
        trade_date (str): The trade date in ``YYYY-MM-DD`` form.
        decision (str): The final decision text from the signal processor.
    """
    color_map = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}
    color = color_map.get(decision.strip().upper(), "magenta")
    console.print(
        Panel(
            Text(decision, style=f"bold {color}"),
            title=f"[bold]Final Decision · {ticker} · {trade_date}[/bold]",
            border_style=color,
            padding=(1, 2),
            expand=True,
        )
    )


__all__ = ["console", "pretty_print_message", "print_decision", "print_header", "print_summary"]
