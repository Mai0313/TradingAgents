from typing import Any

from rich.console import Console, RenderableType
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

from tradingagents.interface.display import MessageRenderer


def _render_to_text(renderables: list[RenderableType]) -> str:
    console = Console(record=True, width=120)
    for renderable in renderables:
        console.print(renderable)
    return console.export_text()


def test_message_renderer_skips_continue_placeholder() -> None:
    emitted: list[RenderableType] = []
    renderer = MessageRenderer(emit=emitted.append)

    renderer.render(HumanMessage(content="Continue"))

    assert emitted == []


def test_message_renderer_renders_ai_tool_calls() -> None:
    emitted: list[RenderableType] = []
    renderer = MessageRenderer(emit=emitted.append)

    renderer.render(
        AIMessage(
            content="Need market data.",
            name="Market Analyst",
            tool_calls=[{"name": "get_stock_data", "args": {"ticker": "AAPL"}, "id": "call-1"}],
        )
    )

    output = _render_to_text(emitted)
    assert "AI - Market Analyst" in output
    assert "Need market data." in output
    assert "Tool Calls" in output
    assert "get_stock_data" in output
    assert '"ticker": "AAPL"' in output


def test_message_renderer_pretty_prints_tool_json() -> None:
    emitted: list[RenderableType] = []
    renderer = MessageRenderer(emit=emitted.append)

    renderer.render(
        ToolMessage(
            content='{"ticker": "AAPL", "close": 195.12}',
            name="get_stock_data",
            tool_call_id="call-1",
        )
    )

    output = _render_to_text(emitted)
    assert "Tool - get_stock_data" in output
    assert '"ticker"' in output
    assert '"AAPL"' in output
    assert "195.12" in output


def test_message_renderer_truncates_long_tool_text() -> None:
    emitted: list[RenderableType] = []
    renderer = MessageRenderer(emit=emitted.append)
    long_text = "\n".join(f"line-{i}" for i in range(45))

    renderer.render(ToolMessage(content=long_text, name="long_tool", tool_call_id="call-1"))

    output = _render_to_text(emitted)
    assert "line-0" in output
    assert "line-39" in output
    assert "line-44" not in output
    assert "5 more lines truncated" in output


def test_content_to_renderable_flattens_text_blocks() -> None:
    emitted: list[RenderableType] = []
    renderer = MessageRenderer(emit=emitted.append)
    content: list[Any] = [{"type": "text", "text": "chunk one"}, {"type": "text", "text": "chunk two"}]

    renderer.render(AIMessage(content=content))

    output = _render_to_text(emitted)
    assert "chunk one" in output
    assert "chunk two" in output
