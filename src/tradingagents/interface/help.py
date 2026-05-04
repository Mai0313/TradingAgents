"""Rich-based help renderer for the tradingagents console script.

Replaces the default fire help screen (which drops the user into a
pager session reminiscent of less / vim) with inline Rich panels
printed straight to stdout. Used by :func:`tradingagents.__main__.main`
whenever it detects a --help / -h / help argument or no arguments at
all.
"""

from __future__ import annotations

import re
import typing
from typing import Any, Literal, get_args, get_origin
import inspect

from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.markup import escape

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from rich.console import Console

PROG_NAME = "tradingagents"
PROG_DESCRIPTION = "Multi-Agents LLM Financial Trading Framework."


def print_app_help(console: Console, commands: dict[str, Callable[..., Any]]) -> None:
    """Render the top-level tradingagents help.

    Args:
        console (Console): The Rich console to draw on.
        commands (dict[str, Callable[..., Any]]): Subcommand name to
            implementing callable. The callable's docstring summary is
            used as the per-row description.
    """
    console.print(
        Panel(
            Text(PROG_DESCRIPTION, style="bold"),
            title=f"[bold cyan]{PROG_NAME}[/]",
            title_align="left",
            border_style="cyan",
        )
    )

    table = Table(show_header=True, header_style="bold", expand=True, padding=(0, 1))
    table.add_column("Command", style="bold cyan", no_wrap=True)
    table.add_column("Description", overflow="fold")
    for name, fn in commands.items():
        table.add_row(name, _docstring_summary(fn))
    console.print(
        Panel(table, title="[bold]Commands[/]", title_align="left", border_style="bright_blue")
    )

    usage = Text()
    usage.append("Usage\n", style="bold")
    usage.append(f"  {PROG_NAME} <command> [--flag value ...]\n", style="cyan")
    usage.append(f"  {PROG_NAME} <command> --help", style="cyan")
    usage.append("    # show flags for a specific command\n", style="dim")
    usage.append(f"  {PROG_NAME} help <command>", style="cyan")
    usage.append("     # equivalent\n", style="dim")
    console.print(usage)


def print_command_help(console: Console, name: str, fn: Callable[..., Any]) -> None:
    """Render help for a single subcommand.

    Args:
        console (Console): The Rich console to draw on.
        name (str): The subcommand name (cli or tui).
        fn (Callable[..., Any]): The implementing callable. Type
            annotations and Google-style docstring are parsed to
            populate the flags table.
    """
    summary = _docstring_summary(fn)
    if summary:
        console.print(
            Panel(
                Text(summary, style="bold"),
                title=f"[bold cyan]{PROG_NAME} {name}[/]",
                title_align="left",
                border_style="cyan",
            )
        )

    sig = inspect.signature(fn)
    descriptions = _parse_google_args(inspect.getdoc(fn))
    try:
        hints = typing.get_type_hints(fn)
    except (NameError, TypeError):
        hints = {}

    table = Table(show_header=True, header_style="bold", expand=True, padding=(0, 1))
    table.add_column("Flag", style="bold cyan", no_wrap=True)
    table.add_column("Type", style="yellow", no_wrap=False, overflow="fold")
    table.add_column("Default", style="magenta", no_wrap=False, overflow="fold")
    table.add_column("Description", overflow="fold")

    for arg_name, param in sig.parameters.items():
        if param.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            continue
        flag = f"--{arg_name}"
        annotation = hints.get(arg_name, param.annotation)
        type_str = escape(_format_type(annotation))
        default = escape(_format_default(param.default))
        desc = escape(descriptions.get(arg_name, ""))
        table.add_row(flag, type_str, default, desc)

    console.print(
        Panel(table, title="[bold]Flags[/]", title_align="left", border_style="bright_blue")
    )

    examples = Text()
    examples.append("Examples\n", style="bold")
    examples.append(f"  {PROG_NAME} {name}\n", style="cyan")
    if name == "cli":
        examples.append(
            f"  {PROG_NAME} {name} --ticker AAPL --deep_think_llm gpt-5\n", style="cyan"
        )
        examples.append(
            f'  {PROG_NAME} {name} --selected_analysts \'["market","news"]\'\n', style="cyan"
        )
    console.print(examples)


def _docstring_summary(fn: Callable[..., Any]) -> str:
    """Return the first line of a function's docstring.

    Args:
        fn (Callable[..., Any]): The function to inspect.

    Returns:
        str: The first non-empty line of the docstring, or an empty
        string when there is no docstring.
    """
    doc = inspect.getdoc(fn) or ""
    return doc.split("\n", 1)[0].strip()


_ARG_LINE = re.compile(r"^    (\w+)\s*(?:\([^)]*\))?:\s*(.*)$")
_SECTION_HEADER = re.compile(
    r"^(Returns?|Yields?|Raises?|Examples?|Attributes?|Note|Warning):\s*$", re.MULTILINE
)


def _parse_google_args(docstring: str | None) -> dict[str, str]:
    """Extract per-argument descriptions from a Google-style docstring.

    Args:
        docstring (str | None): The raw docstring text.

    Returns:
        dict[str, str]: A mapping from argument name to its concatenated
        description text, with continuation lines joined into a single
        string. Returns an empty dict when the docstring has no Args
        section.
    """
    if not docstring:
        return {}

    doc = inspect.cleandoc(docstring)
    args_match = re.search(r"^Args:\s*$", doc, re.MULTILINE)
    if not args_match:
        return {}

    rest = doc[args_match.end() :]
    next_section = _SECTION_HEADER.search(rest)
    args_block = rest[: next_section.start()] if next_section else rest

    descriptions: dict[str, str] = {}
    current_name: str | None = None
    current_desc: list[str] = []

    for line in args_block.splitlines():
        if not line.strip():
            continue
        m = _ARG_LINE.match(line)
        if m:
            if current_name is not None:
                descriptions[current_name] = " ".join(current_desc).strip()
            current_name = m.group(1)
            current_desc = [m.group(2)]
        else:
            current_desc.append(line.strip())

    if current_name is not None:
        descriptions[current_name] = " ".join(current_desc).strip()

    return descriptions


def _format_type(annotation: Any) -> str:  # noqa: ANN401
    """Render a type annotation as a short, terminal-friendly string.

    Literal types are expanded into a pipe-separated enum so users see
    the allowed values directly; bare classes show their __name__;
    everything else falls back to str(annotation) with the typing.
    prefix stripped.

    Args:
        annotation (Any): The annotation as returned by
            :func:`inspect.signature` or :func:`typing.get_type_hints`.

    Returns:
        str: A printable representation of the annotation.
    """
    if annotation is inspect.Parameter.empty:
        return "any"
    if get_origin(annotation) is Literal:
        return " | ".join(repr(a) for a in get_args(annotation))
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _format_default(default: Any) -> str:  # noqa: ANN401
    """Render a default value for the help table.

    Args:
        default (Any): The parameter's default, or
            :attr:`inspect.Parameter.empty` for required arguments.

    Returns:
        str: "(required)" when no default is set, otherwise repr(default).
    """
    if default is inspect.Parameter.empty:
        return "(required)"
    return repr(default)
