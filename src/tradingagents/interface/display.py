"""Rich-based renderers for the TradingAgents CLI / TUI.

Replaces langchain_core.messages.BaseMessage.pretty_print (the
"=== Ai Message ===" text blocks streamed during a graph run) with
Rich panels: colour-coded by message type, Markdown-rendered for agent
prose, JSON-pretty-printed for structured tool output, and truncated
when the underlying content would otherwise spam the terminal (raw
stock data tool responses can be thousands of lines).

The renderer is target-agnostic: ``MessageRenderer.emit`` receives a
Rich renderable (Panel, Markdown, Text, ...). The CLI passes
``Console.print`` so panels go to stdout; the TUI passes a thread-safe
``RichLog.write`` wrapper so the same panels are appended to a
reflow-aware scrollable widget instead.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from collections.abc import Callable  # noqa: TC003  # runtime-required by Pydantic field type

from pydantic import Field, BaseModel, ConfigDict
from rich.json import JSON
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.console import Group, Console, RenderableType
from rich.markdown import Markdown
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage, SystemMessage

if TYPE_CHECKING:
    from langchain_core.messages import AnyMessage

    from tradingagents.config import TradingAgentsConfig
    from tradingagents.graph.signal_processing import TradeRecommendation


_MAX_TOOL_LINES = 40


class MessageRenderer(BaseModel):
    """Render LangChain messages as Rich panels via a pluggable emit target.

    A single instance is reused across a run so the HumanMessage
    "Continue" placeholders (graph plumbing for Anthropic's
    message-ordering rules) can be filtered out, matching the behaviour
    of TradingAgentsGraph._save_conversation_log.

    Attributes:
        emit (Callable[[RenderableType], None]): Receives each rendered
            Rich renderable. CLI passes ``Console.print``; TUI passes a
            thread-safe ``RichLog.write`` wrapper that defers writes to
            the Textual main thread via ``App.call_from_thread``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    emit: Callable[[RenderableType], None] = Field(
        ...,
        title="Emit Callback",
        description=(
            "Sink for each rendered Rich renderable. CLI uses Console.print; "
            "TUI uses a RichLog.write wrapper that hops to the main thread."
        ),
    )

    @classmethod
    def for_console(cls, console: Console | None = None) -> MessageRenderer:
        """Build a renderer that prints each panel via Rich Console.

        Args:
            console (Console | None, optional): The Rich console to write
                to. Defaults to a new console bound to stdout.

        Returns:
            MessageRenderer: A renderer whose ``emit`` is bound to the
            console's print method.
        """
        target = console or Console()
        return cls(emit=target.print)

    def __call__(self, message: AnyMessage) -> None:
        """Alias for :meth:`render` so the renderer can be passed as a callback.

        Args:
            message (AnyMessage): The LangChain message to render.
        """
        self.render(message)

    def render(self, message: AnyMessage) -> None:
        """Render a single LangChain message.

        Args:
            message (AnyMessage): The LangChain message to render. Unknown
                message types fall through to a generic panel.
        """
        if isinstance(message, HumanMessage):
            if isinstance(message.content, str) and message.content.strip() == "Continue":
                return
            self._render_human(message)
        elif isinstance(message, AIMessage):
            self._render_ai(message)
        elif isinstance(message, ToolMessage):
            self._render_tool(message)
        elif isinstance(message, SystemMessage):
            self._render_system(message)
        else:
            self._render_unknown(message)

    def _render_ai(self, message: AIMessage) -> None:
        """Render an AIMessage (assistant turn).

        Args:
            message (AIMessage): The assistant message, which may contain
                Markdown content and/or tool calls.
        """
        body = self._content_to_renderable(message.content)
        renderables: list[RenderableType] = [body] if body is not None else []

        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            table = Table(
                title="Tool Calls",
                title_style="bold yellow",
                show_header=True,
                header_style="bold",
                expand=True,
            )
            table.add_column("Tool", style="bold cyan", no_wrap=True)
            table.add_column("Args", overflow="fold")
            for call in tool_calls:
                name = str(call.get("name", "?"))
                args = call.get("args", {})
                args_text = json.dumps(args, ensure_ascii=False, indent=2)
                table.add_row(name, args_text)
            renderables.append(table)

        if not renderables:
            renderables.append(Text("(no content)", style="dim italic"))

        title = "AI"
        agent_name = getattr(message, "name", None)
        if agent_name:
            title = f"AI - {agent_name}"

        self.emit(
            Panel(
                Group(*renderables),
                title=f"[bold cyan]{title}[/]",
                title_align="left",
                border_style="cyan",
            )
        )

    def _render_human(self, message: HumanMessage) -> None:
        """Render a HumanMessage (user turn).

        Args:
            message (HumanMessage): The human-authored message.
        """
        body = self._content_to_renderable(message.content) or Text("(no content)", style="dim")
        self.emit(
            Panel(body, title="[bold green]Human[/]", title_align="left", border_style="green")
        )

    def _render_tool(self, message: ToolMessage) -> None:
        """Render a ToolMessage (tool execution result).

        Args:
            message (ToolMessage): The tool result message. Content is
                pretty-printed as JSON when parseable, otherwise truncated
                plain text.
        """
        name = getattr(message, "name", None) or "tool"
        body = self._tool_content_to_renderable(message.content)
        self.emit(
            Panel(
                body,
                title=f"[bold yellow]Tool - {name}[/]",
                title_align="left",
                border_style="yellow",
            )
        )

    def _render_system(self, message: SystemMessage) -> None:
        """Render a SystemMessage (system / role prompt).

        Args:
            message (SystemMessage): The system message.
        """
        body = self._content_to_renderable(message.content) or Text("(no content)", style="dim")
        self.emit(
            Panel(body, title="[bold]System[/]", title_align="left", border_style="bright_black")
        )

    def _render_unknown(self, message: AnyMessage) -> None:
        """Render any non-standard message type with a generic panel.

        Args:
            message (AnyMessage): A LangChain message whose type does not
                match the known subclasses.
        """
        kind = getattr(message, "type", message.__class__.__name__)
        body = self._content_to_renderable(getattr(message, "content", "")) or Text(
            "(no content)", style="dim"
        )
        self.emit(Panel(body, title=f"[bold]{kind}[/]", title_align="left", border_style="white"))

    @staticmethod
    def _content_to_renderable(content: Any) -> RenderableType | None:  # noqa: ANN401
        """Convert a LangChain message content payload into a Rich renderable.

        Args:
            content (Any): A string, a list of content blocks (Anthropic /
                Gemini multimodal style), or any other JSON-serializable
                value.

        Returns:
            RenderableType | None: A Rich renderable (typically a Markdown
            block for prose), or None when the content is empty.
        """
        if content is None:
            return None
        if isinstance(content, str):
            text = content.strip()
            if not text:
                return None
            return Markdown(text)
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False, default=str))
            joined = "\n".join(parts).strip()
            if not joined:
                return None
            return Markdown(joined)
        return Text(str(content))

    @staticmethod
    def _tool_content_to_renderable(content: Any) -> RenderableType:  # noqa: ANN401
        """Render tool output: JSON when possible, truncated text otherwise.

        Args:
            content (Any): The raw ToolMessage.content payload.

        Returns:
            RenderableType: A JSON renderable for structured output, or a
            plain Text block (truncated to _MAX_TOOL_LINES) for free-form
            text.
        """
        text = content if isinstance(content, str) else json.dumps(content, default=str)
        stripped = text.strip()
        if not stripped:
            return Text("(empty)", style="dim italic")

        if stripped[:1] in {"{", "["}:
            try:
                return JSON(stripped)
            except (ValueError, json.JSONDecodeError):
                pass

        lines = stripped.splitlines()
        if len(lines) > _MAX_TOOL_LINES:
            head = "\n".join(lines[:_MAX_TOOL_LINES])
            footer = f"\n... [{len(lines) - _MAX_TOOL_LINES} more lines truncated]"
            return Text(head + footer)
        return Text(stripped)


def make_run_header_panel(*, ticker: str, trade_date: str, config: TradingAgentsConfig) -> Panel:
    """Build a Rich panel summarising the upcoming run.

    Shared by the CLI (printed once at startup) and the TUI (mounted as
    the persistent header content).

    Args:
        ticker (str): The stock ticker / company being analysed.
        trade_date (str): Trade date in YYYY-MM-DD format.
        config (TradingAgentsConfig): The active configuration; selected
            fields are surfaced in a two-column table.

    Returns:
        Panel: The composed Rich panel.
    """
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    table.add_row("Ticker", ticker)
    table.add_row("Trade Date", trade_date)
    table.add_row("LLM Provider", config.llm_provider)
    table.add_row("Deep Think LLM", config.deep_think_llm)
    table.add_row("Quick Think LLM", config.quick_think_llm)
    table.add_row("Reasoning Effort", config.reasoning_effort)
    table.add_row("Response Language", config.response_language)
    table.add_row("Max Debate Rounds", str(config.max_debate_rounds))
    table.add_row("Max Risk Discuss Rounds", str(config.max_risk_discuss_rounds))
    table.add_row("Max Recursion Limit", str(config.max_recur_limit))
    table.add_row("Results Dir", str(config.results_dir))
    return Panel(
        table,
        title="[bold]TradingAgents - Run Configuration[/]",
        title_align="left",
        border_style="bright_blue",
    )


_SIGNAL_STYLES: dict[str, str] = {"BUY": "bold green", "SELL": "bold red", "HOLD": "bold yellow"}


def make_final_decision_panel(recommendation: TradeRecommendation) -> Panel:
    """Build the highlighted final-decision panel from a :class:`TradeRecommendation`.

    Surfaces every structured field (signal, size, target, stop, horizon,
    confidence, rationale) plus a warning_message banner when the parser
    had to fall back. A bare-string fallback path is kept so legacy
    callers passing a plain decision string still get a sensible panel.

    Args:
        recommendation (TradeRecommendation): The structured recommendation
            returned by ``SignalProcessor.process_signal``.

    Returns:
        Panel: The composed Rich panel.
    """
    signal = recommendation.signal
    style = _SIGNAL_STYLES.get(signal, "bold")

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    table.add_row("Signal", Text(signal, style=style))
    table.add_row("Size fraction", f"{recommendation.size_fraction:.2f}")
    if recommendation.target_price is not None:
        table.add_row("Target price", f"{recommendation.target_price:g}")
    if recommendation.stop_loss is not None:
        table.add_row("Stop loss", f"{recommendation.stop_loss:g}")
    if recommendation.time_horizon_days is not None:
        table.add_row("Time horizon", f"{recommendation.time_horizon_days}d")
    table.add_row("Confidence", f"{recommendation.confidence:.2f}")
    if recommendation.rationale:
        table.add_row("Rationale", recommendation.rationale)

    renderables: list[RenderableType] = [table]
    if recommendation.warning_message:
        renderables.append(Text(f"⚠ {recommendation.warning_message}", style="bold yellow"))

    return Panel(
        Group(*renderables),
        title="[bold magenta]Final Trade Decision[/]",
        title_align="left",
        border_style="magenta",
    )


def print_run_header(
    console: Console, *, ticker: str, trade_date: str, config: TradingAgentsConfig
) -> None:
    """Print the run header panel to a Rich console.

    Args:
        console (Console): The Rich console to print on.
        ticker (str): The stock ticker / company being analysed.
        trade_date (str): Trade date in YYYY-MM-DD format.
        config (TradingAgentsConfig): The active configuration.
    """
    console.print(make_run_header_panel(ticker=ticker, trade_date=trade_date, config=config))


def print_final_decision(console: Console, recommendation: TradeRecommendation) -> None:
    """Print the final structured-recommendation panel to a Rich console.

    Args:
        console (Console): The Rich console to print on.
        recommendation (TradeRecommendation): The structured recommendation
            returned by ``SignalProcessor.process_signal``.
    """
    console.print(make_final_decision_panel(recommendation))
