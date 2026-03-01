import ast
import time
from typing import TYPE_CHECKING, Any, ClassVar
from pathlib import Path
import datetime
from collections import deque

from rich import box
import typer
from dotenv import load_dotenv
from rich.live import Live
from rich.rule import Rule
from rich.text import Text
from rich.align import Align
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.console import Console
from rich.spinner import Spinner
from rich.markdown import Markdown
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

from tradingagents.cli.utils import (
    get_ticker,
    select_analysts,
    get_analysis_date,
    select_llm_provider,
    select_research_depth,
    ask_gemini_thinking_config,
    select_deep_thinking_agent,
    ask_openai_reasoning_effort,
    select_shallow_thinking_agent,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.cli.announcements import fetch_announcements, display_announcements
from tradingagents.cli.stats_handler import StatsCallbackHandler
from tradingagents.graph.trading_graph import TradingAgentsGraph

if TYPE_CHECKING:
    from collections.abc import Callable

# Load environment variables from .env file
load_dotenv()

console = Console()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Financial Trading Framework",
    add_completion=True,  # Enable shell completion
)


# Create a deque to store recent messages with a maximum length
class MessageBuffer:
    # Fixed teams that always run (not user-selectable)
    FIXED_AGENTS: ClassVar[dict[str, list[str]]] = {
        "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "Trading Team": ["Trader"],
        "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
        "Portfolio Management": ["Portfolio Manager"],
    }

    # Analyst name mapping
    ANALYST_MAPPING: ClassVar[dict[str, str]] = {
        "market": "Market Analyst",
        "social": "Social Analyst",
        "news": "News Analyst",
        "fundamentals": "Fundamentals Analyst",
    }

    # Report section mapping: section -> (analyst_key for filtering, finalizing_agent)
    # analyst_key: which analyst selection controls this section (None = always included)
    # finalizing_agent: which agent must be "completed" for this report to count as done
    REPORT_SECTIONS: ClassVar[dict[str, tuple[str | None, str]]] = {
        "market_report": ("market", "Market Analyst"),
        "sentiment_report": ("social", "Social Analyst"),
        "news_report": ("news", "News Analyst"),
        "fundamentals_report": ("fundamentals", "Fundamentals Analyst"),
        "investment_plan": (None, "Research Manager"),
        "trader_investment_plan": (None, "Trader"),
        "final_trade_decision": (None, "Portfolio Manager"),
    }

    def __init__(self, max_length: int = 100) -> None:
        self.messages: deque[tuple[str, str, str]] = deque(maxlen=max_length)
        self.tool_calls: deque[tuple[str, str, Any]] = deque(maxlen=max_length)
        self.current_report: str | None = None
        self.final_report: str | None = None  # Store the complete final report
        self.agent_status: dict[str, str] = {}
        self.current_agent: str | None = None
        self.report_sections: dict[str, str | None] = {}
        self.selected_analysts: list[str] = []
        self._last_message_id: str | None = None
        # Optional hooks called after the corresponding methods
        self.on_add_message: Callable[[str, str, str], None] | None = None
        self.on_add_tool_call: Callable[[str, str, object], None] | None = None
        self.on_update_report_section: Callable[[str, str | None], None] | None = None

    def init_for_analysis(self, selected_analysts: list[str]) -> None:
        """Initialize agent status and report sections based on selected analysts.

        Args:
            selected_analysts: List of analyst type strings (e.g., ["market", "news"])
        """
        self.selected_analysts = [a.lower() for a in selected_analysts]

        # Build agent_status dynamically
        self.agent_status = {}

        # Add selected analysts
        for analyst_key in self.selected_analysts:
            if analyst_key in self.ANALYST_MAPPING:
                self.agent_status[self.ANALYST_MAPPING[analyst_key]] = "pending"

        # Add fixed teams
        for team_agents in self.FIXED_AGENTS.values():
            for agent in team_agents:
                self.agent_status[agent] = "pending"

        # Build report_sections dynamically
        self.report_sections = {}
        for section, (analyst_key, _) in self.REPORT_SECTIONS.items():
            if analyst_key is None or analyst_key in self.selected_analysts:
                self.report_sections[section] = None

        # Reset other state
        self.current_report = None
        self.final_report = None
        self.current_agent = None
        self.messages.clear()
        self.tool_calls.clear()
        self._last_message_id = None

    def get_last_message_id(self) -> str | None:
        """Get the ID of the last processed message."""
        return self._last_message_id

    def set_last_message_id(self, msg_id: str | None) -> None:
        """Set the ID of the last processed message."""
        self._last_message_id = msg_id

    def get_completed_reports_count(self) -> int:
        """Count reports that are finalized (their finalizing agent is completed).

        A report is considered complete when:
        1. The report section has content (not None), AND
        2. The agent responsible for finalizing that report has status "completed"

        This prevents interim updates (like debate rounds) from counting as completed.
        """
        count = 0
        for section in self.report_sections:
            if section not in self.REPORT_SECTIONS:
                continue
            _, finalizing_agent = self.REPORT_SECTIONS[section]
            # Report is complete if it has content AND its finalizing agent is done
            has_content = self.report_sections.get(section) is not None
            agent_done = self.agent_status.get(finalizing_agent) == "completed"
            if has_content and agent_done:
                count += 1
        return count

    def add_message(self, message_type: str, content: str) -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, message_type, content))
        if self.on_add_message is not None:
            self.on_add_message(timestamp, message_type, content)

    def add_tool_call(self, tool_name: str, args: object) -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.tool_calls.append((timestamp, tool_name, args))
        if self.on_add_tool_call is not None:
            self.on_add_tool_call(timestamp, tool_name, args)

    def update_agent_status(self, agent: str, status: str) -> None:
        if agent in self.agent_status:
            self.agent_status[agent] = status
            self.current_agent = agent

    def update_report_section(self, section_name: str, content: str) -> None:
        if section_name in self.report_sections:
            self.report_sections[section_name] = content
            self._update_current_report()
            if self.on_update_report_section is not None:
                self.on_update_report_section(section_name, self.report_sections[section_name])

    def _update_current_report(self) -> None:
        # For the panel display, only show the most recently updated section
        latest_section = None
        latest_content = None

        # Find the most recently updated section
        for section, content in self.report_sections.items():
            if content is not None:
                latest_section = section
                latest_content = content

        if latest_section and latest_content:
            # Format the current section for display
            section_titles = {
                "market_report": "Market Analysis",
                "sentiment_report": "Social Sentiment",
                "news_report": "News Analysis",
                "fundamentals_report": "Fundamentals Analysis",
                "investment_plan": "Research Team Decision",
                "trader_investment_plan": "Trading Team Plan",
                "final_trade_decision": "Portfolio Management Decision",
            }
            self.current_report = f"### {section_titles[latest_section]}\n{latest_content}"

        # Update the final complete report
        self._update_final_report()

    def _update_final_report(self) -> None:
        report_parts = []

        # Analyst Team Reports - use .get() to handle missing sections
        analyst_sections = [
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
        ]
        if any(self.report_sections.get(section) for section in analyst_sections):
            report_parts.append("## Analyst Team Reports")
            if self.report_sections.get("market_report"):
                report_parts.append(
                    f"### Market Analysis\n{self.report_sections['market_report']}"
                )
            if self.report_sections.get("sentiment_report"):
                report_parts.append(
                    f"### Social Sentiment\n{self.report_sections['sentiment_report']}"
                )
            if self.report_sections.get("news_report"):
                report_parts.append(f"### News Analysis\n{self.report_sections['news_report']}")
            if self.report_sections.get("fundamentals_report"):
                report_parts.append(
                    f"### Fundamentals Analysis\n{self.report_sections['fundamentals_report']}"
                )

        # Research Team Reports
        if self.report_sections.get("investment_plan"):
            report_parts.append("## Research Team Decision")
            report_parts.append(f"{self.report_sections['investment_plan']}")

        # Trading Team Reports
        if self.report_sections.get("trader_investment_plan"):
            report_parts.append("## Trading Team Plan")
            report_parts.append(f"{self.report_sections['trader_investment_plan']}")

        # Portfolio Management Decision
        if self.report_sections.get("final_trade_decision"):
            report_parts.append("## Portfolio Management Decision")
            report_parts.append(f"{self.report_sections['final_trade_decision']}")

        self.final_report = "\n\n".join(report_parts) if report_parts else None


message_buffer = MessageBuffer()


def create_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3), Layout(name="main"), Layout(name="footer", size=3)
    )
    layout["main"].split_column(Layout(name="upper", ratio=3), Layout(name="analysis", ratio=5))
    layout["upper"].split_row(Layout(name="progress", ratio=2), Layout(name="messages", ratio=3))
    return layout


def format_tokens(n: int) -> str:
    """Format token count for display."""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _get_status_cell(status: str) -> Spinner | str:
    """Return a Rich renderable for an agent status."""
    if status == "in_progress":
        return Spinner("dots", text="[blue]in_progress[/blue]", style="bold cyan")
    status_color = {"pending": "yellow", "completed": "green", "error": "red"}.get(status, "white")
    return f"[{status_color}]{status}[/{status_color}]"


def _build_progress_table() -> Table:
    """Build the agent progress table."""
    progress_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        box=box.SIMPLE_HEAD,
        title=None,
        padding=(0, 2),
        expand=True,
    )
    progress_table.add_column("Team", style="cyan", justify="center", width=20)
    progress_table.add_column("Agent", style="green", justify="center", width=20)
    progress_table.add_column("Status", style="yellow", justify="center", width=20)

    all_teams = {
        "Analyst Team": [
            "Market Analyst",
            "Social Analyst",
            "News Analyst",
            "Fundamentals Analyst",
        ],
        "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "Trading Team": ["Trader"],
        "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
        "Portfolio Management": ["Portfolio Manager"],
    }

    teams = {
        team: [a for a in agents if a in message_buffer.agent_status]
        for team, agents in all_teams.items()
        if any(a in message_buffer.agent_status for a in agents)
    }

    for team, agents in teams.items():
        first_agent = agents[0]
        status = message_buffer.agent_status.get(first_agent, "pending")
        progress_table.add_row(team, first_agent, _get_status_cell(status))
        for agent in agents[1:]:
            agent_status = message_buffer.agent_status.get(agent, "pending")
            progress_table.add_row("", agent, _get_status_cell(agent_status))
        progress_table.add_row("─" * 20, "─" * 20, "─" * 20, style="dim")

    return progress_table


def _build_messages_table() -> Table:
    """Build the messages and tool calls table."""
    messages_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        expand=True,
        box=box.MINIMAL,
        show_lines=True,
        padding=(0, 1),
    )
    messages_table.add_column("Time", style="cyan", width=8, justify="center")
    messages_table.add_column("Type", style="green", width=10, justify="center")
    messages_table.add_column("Content", style="white", no_wrap=False, ratio=1)

    all_messages: list[tuple[str, str, str]] = []
    for timestamp, tool_name, args in message_buffer.tool_calls:
        formatted_args = format_tool_args(args)
        all_messages.append((timestamp, "Tool", f"{tool_name}: {formatted_args}"))
    for timestamp, msg_type, content in message_buffer.messages:
        content_str = str(content) if content else ""
        if len(content_str) > 200:
            content_str = content_str[:197] + "..."
        all_messages.append((timestamp, msg_type, content_str))

    all_messages.sort(key=lambda x: x[0], reverse=True)
    for timestamp, msg_type, content in all_messages[:12]:
        messages_table.add_row(timestamp, msg_type, Text(content, overflow="fold"))
    return messages_table


def _build_footer(stats_handler: StatsCallbackHandler | None, start_time: float | None) -> Panel:
    """Build the footer statistics panel."""
    agents_completed = sum(
        1 for status in message_buffer.agent_status.values() if status == "completed"
    )
    agents_total = len(message_buffer.agent_status)
    reports_completed = message_buffer.get_completed_reports_count()
    reports_total = len(message_buffer.report_sections)

    stats_parts = [f"Agents: {agents_completed}/{agents_total}"]
    if stats_handler:
        stats = stats_handler.get_stats()
        stats_parts.append(f"LLM: {stats['llm_calls']}")
        stats_parts.append(f"Tools: {stats['tool_calls']}")
        if stats["tokens_in"] > 0 or stats["tokens_out"] > 0:
            tokens_str = f"Tokens: {format_tokens(stats['tokens_in'])}\u2191 {format_tokens(stats['tokens_out'])}\u2193"
        else:
            tokens_str = "Tokens: --"
        stats_parts.append(tokens_str)
    stats_parts.append(f"Reports: {reports_completed}/{reports_total}")
    if start_time:
        elapsed = time.time() - start_time
        stats_parts.append(f"\u23f1 {int(elapsed // 60):02d}:{int(elapsed % 60):02d}")

    stats_table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    stats_table.add_column("Stats", justify="center")
    stats_table.add_row(" | ".join(stats_parts))
    return Panel(stats_table, border_style="grey50")


def update_display(
    layout: Layout,
    spinner_text: str | None = None,
    stats_handler: StatsCallbackHandler | None = None,
    start_time: float | None = None,
) -> None:
    """Update the Rich live display layout."""
    layout["header"].update(
        Panel(
            "[bold green]Welcome to TradingAgents CLI[/bold green]\n"
            "[dim]© [Tauric Research](https://github.com/TauricResearch)[/dim]",
            title="Welcome to TradingAgents",
            border_style="green",
            padding=(1, 2),
            expand=True,
        )
    )
    layout["progress"].update(
        Panel(_build_progress_table(), title="Progress", border_style="cyan", padding=(1, 2))
    )
    layout["messages"].update(
        Panel(
            _build_messages_table(), title="Messages & Tools", border_style="blue", padding=(1, 2)
        )
    )
    if message_buffer.current_report:
        layout["analysis"].update(
            Panel(
                Markdown(message_buffer.current_report),
                title="Current Report",
                border_style="green",
                padding=(1, 2),
            )
        )
    else:
        layout["analysis"].update(
            Panel(
                "[italic]Waiting for analysis report...[/italic]",
                title="Current Report",
                border_style="green",
                padding=(1, 2),
            )
        )
    layout["footer"].update(_build_footer(stats_handler, start_time))


def get_user_selections() -> dict[str, Any]:
    """Get all user selections before starting the analysis display."""
    # Display ASCII art welcome message
    with open(Path(__file__).parent / "static/welcome.txt") as f:
        welcome_ascii = f.read()

    # Create welcome box content
    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgents: Multi-Agents LLM Financial Trading Framework - CLI[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += "I. Analyst Team → II. Research Team → III. Trader → IV. Risk Management → V. Portfolio Management\n\n"
    welcome_content += "[dim]Built by [Tauric Research](https://github.com/TauricResearch)[/dim]"

    # Create and center the welcome box
    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to TradingAgents",
        subtitle="Multi-Agents LLM Financial Trading Framework",
    )
    console.print(Align.center(welcome_box))
    console.print()
    console.print()  # Add vertical space before announcements

    # Fetch and display announcements (silent on failure)
    announcements = fetch_announcements()
    display_announcements(console, announcements)

    # Create a boxed questionnaire for each step
    def create_question_box(title: str, prompt: str, default: str | None = None) -> Panel:
        box_content = f"[bold]{title}[/bold]\n"
        box_content += f"[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]Default: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    # Step 1: Ticker symbol
    console.print(
        create_question_box("Step 1: Ticker Symbol", "Enter the ticker symbol to analyze", "SPY")
    )
    selected_ticker = get_ticker()

    # Step 2: Analysis date
    default_date = datetime.datetime.now().strftime("%Y-%m-%d")
    console.print(
        create_question_box(
            "Step 2: Analysis Date", "Enter the analysis date (YYYY-MM-DD)", default_date
        )
    )
    analysis_date = get_analysis_date()

    # Step 3: Select analysts
    console.print(
        create_question_box(
            "Step 3: Analysts Team", "Select your LLM analyst agents for the analysis"
        )
    )
    selected_analysts = select_analysts()
    console.print(
        f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    # Step 4: Research depth
    console.print(
        create_question_box("Step 4: Research Depth", "Select your research depth level")
    )
    selected_research_depth = select_research_depth()

    # Step 5: OpenAI backend
    console.print(create_question_box("Step 5: OpenAI backend", "Select which service to talk to"))
    selected_llm_provider, backend_url = select_llm_provider()

    # Step 6: Thinking agents
    console.print(
        create_question_box("Step 6: Thinking Agents", "Select your thinking agents for analysis")
    )
    selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
    selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)

    # Step 7: Provider-specific thinking configuration
    thinking_level = None
    reasoning_effort = None

    provider_lower = selected_llm_provider.lower()
    if provider_lower == "google":
        console.print(
            create_question_box("Step 7: Thinking Mode", "Configure Gemini thinking mode")
        )
        thinking_level = ask_gemini_thinking_config()
    elif provider_lower == "openai":
        console.print(
            create_question_box(
                "Step 7: Reasoning Effort", "Configure OpenAI reasoning effort level"
            )
        )
        reasoning_effort = ask_openai_reasoning_effort()

    return {
        "ticker": selected_ticker,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "deep_thinker": selected_deep_thinker,
        "google_thinking_level": thinking_level,
        "openai_reasoning_effort": reasoning_effort,
    }


def _get_ticker_prompt() -> str:
    """Get ticker symbol from user input via typer prompt."""
    return typer.prompt("", default="SPY")


def _get_analysis_date_prompt() -> str:
    """Get the analysis date from user input via typer prompt."""
    while True:
        date_str = typer.prompt("", default=datetime.datetime.now().strftime("%Y-%m-%d"))
        try:
            # Validate date format and ensure it's not in the future
            analysis_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            if analysis_date.date() > datetime.datetime.now().date():
                console.print("[red]Error: Analysis date cannot be in the future[/red]")
                continue
            return date_str
        except ValueError:
            console.print("[red]Error: Invalid date format. Please use YYYY-MM-DD[/red]")


def _save_analyst_reports(
    final_state: dict[str, Any], analysts_dir: Path
) -> list[tuple[str, str]]:
    """Save analyst reports and return (name, content) pairs."""
    report_map = [
        ("market_report", "market.md", "Market Analyst"),
        ("sentiment_report", "sentiment.md", "Social Analyst"),
        ("news_report", "news.md", "News Analyst"),
        ("fundamentals_report", "fundamentals.md", "Fundamentals Analyst"),
    ]
    parts: list[tuple[str, str]] = []
    for state_key, filename, label in report_map:
        if report := final_state.get(state_key):
            analysts_dir.mkdir(exist_ok=True)
            (analysts_dir / filename).write_text(report)
            parts.append((label, report))
    return parts


def _save_research_reports(
    final_state: dict[str, Any], research_dir: Path
) -> list[tuple[str, str]]:
    """Save research debate reports and return (name, content) pairs."""
    debate = final_state.get("investment_debate_state", {})
    debate_map = [
        ("bull_history", "bull.md", "Bull Researcher"),
        ("bear_history", "bear.md", "Bear Researcher"),
        ("judge_decision", "manager.md", "Research Manager"),
    ]
    parts: list[tuple[str, str]] = []
    for state_key, filename, label in debate_map:
        if content := debate.get(state_key):
            research_dir.mkdir(exist_ok=True)
            (research_dir / filename).write_text(content)
            parts.append((label, content))
    return parts


def _save_risk_reports(
    final_state: dict[str, Any], risk_dir: Path, portfolio_dir: Path
) -> tuple[list[tuple[str, str]], str | None]:
    """Save risk debate reports; return (name, content) pairs and optional judge decision."""
    risk = final_state.get("risk_debate_state", {})
    risk_map = [
        ("aggressive_history", "aggressive.md", "Aggressive Analyst"),
        ("conservative_history", "conservative.md", "Conservative Analyst"),
        ("neutral_history", "neutral.md", "Neutral Analyst"),
    ]
    parts: list[tuple[str, str]] = []
    for state_key, filename, label in risk_map:
        if content := risk.get(state_key):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / filename).write_text(content)
            parts.append((label, content))
    portfolio_decision: str | None = None
    if judge := risk.get("judge_decision"):
        portfolio_dir.mkdir(exist_ok=True)
        (portfolio_dir / "decision.md").write_text(judge)
        portfolio_decision = judge
    return parts, portfolio_decision


def save_report_to_disk(final_state: dict[str, Any], ticker: str, save_path: Path) -> Path:
    """Save complete analysis report to disk with organized subfolders."""
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    # 1. Analysts
    analyst_parts = _save_analyst_reports(final_state, save_path / "1_analysts")
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    # 2. Research
    if final_state.get("investment_debate_state"):
        research_parts = _save_research_reports(final_state, save_path / "2_research")
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. Research Team Decision\n\n{content}")

    # 3. Trading
    if final_state.get("trader_investment_plan"):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(final_state["trader_investment_plan"])
        sections.append(
            f"## III. Trading Team Plan\n\n### Trader\n{final_state['trader_investment_plan']}"
        )

    # 4 & 5. Risk Management & Portfolio Manager
    if final_state.get("risk_debate_state"):
        risk_parts, portfolio_decision = _save_risk_reports(
            final_state, save_path / "4_risk", save_path / "5_portfolio"
        )
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{content}")
        if portfolio_decision:
            sections.append(
                f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{portfolio_decision}"
            )

    # Write consolidated report
    header = f"# Trading Analysis Report: {ticker}\n\nGenerated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    (save_path / "complete_report.md").write_text(header + "\n\n".join(sections))
    return save_path / "complete_report.md"


def _display_analyst_panels(final_state: dict[str, Any]) -> None:
    """Display analyst team report panels."""
    report_map = [
        ("market_report", "Market Analyst"),
        ("sentiment_report", "Social Analyst"),
        ("news_report", "News Analyst"),
        ("fundamentals_report", "Fundamentals Analyst"),
    ]
    analysts = [(label, final_state[key]) for key, label in report_map if final_state.get(key)]
    if analysts:
        console.print(Panel("[bold]I. Analyst Team Reports[/bold]", border_style="cyan"))
        for title, content in analysts:
            console.print(
                Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2))
            )


def _display_research_panels(final_state: dict[str, Any]) -> None:
    """Display research team decision panels."""
    if not final_state.get("investment_debate_state"):
        return
    debate = final_state["investment_debate_state"]
    debate_map = [
        ("bull_history", "Bull Researcher"),
        ("bear_history", "Bear Researcher"),
        ("judge_decision", "Research Manager"),
    ]
    research = [(label, debate[key]) for key, label in debate_map if debate.get(key)]
    if research:
        console.print(Panel("[bold]II. Research Team Decision[/bold]", border_style="magenta"))
        for title, content in research:
            console.print(
                Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2))
            )


def _display_risk_panels(final_state: dict[str, Any]) -> None:
    """Display risk management and portfolio panels."""
    if not final_state.get("risk_debate_state"):
        return
    risk = final_state["risk_debate_state"]
    risk_map = [
        ("aggressive_history", "Aggressive Analyst"),
        ("conservative_history", "Conservative Analyst"),
        ("neutral_history", "Neutral Analyst"),
    ]
    risk_reports = [(label, risk[key]) for key, label in risk_map if risk.get(key)]
    if risk_reports:
        console.print(Panel("[bold]IV. Risk Management Team Decision[/bold]", border_style="red"))
        for title, content in risk_reports:
            console.print(
                Panel(Markdown(content), title=title, border_style="blue", padding=(1, 2))
            )
    if risk.get("judge_decision"):
        console.print(Panel("[bold]V. Portfolio Manager Decision[/bold]", border_style="green"))
        console.print(
            Panel(
                Markdown(risk["judge_decision"]),
                title="Portfolio Manager",
                border_style="blue",
                padding=(1, 2),
            )
        )


def display_complete_report(final_state: dict[str, Any]) -> None:
    """Display the complete analysis report sequentially (avoids truncation)."""
    console.print()
    console.print(Rule("Complete Analysis Report", style="bold green"))
    _display_analyst_panels(final_state)
    _display_research_panels(final_state)
    if final_state.get("trader_investment_plan"):
        console.print(Panel("[bold]III. Trading Team Plan[/bold]", border_style="yellow"))
        console.print(
            Panel(
                Markdown(final_state["trader_investment_plan"]),
                title="Trader",
                border_style="blue",
                padding=(1, 2),
            )
        )
    _display_risk_panels(final_state)


def update_research_team_status(status: str) -> None:
    """Update status for research team members (not Trader)."""
    research_team = ["Bull Researcher", "Bear Researcher", "Research Manager"]
    for agent in research_team:
        message_buffer.update_agent_status(agent, status)


# Ordered list of analysts for status transitions
ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Social Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
ANALYST_REPORT_MAP = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}


def update_analyst_statuses(message_buffer: MessageBuffer, chunk: dict[str, Any]) -> None:
    """Update all analyst statuses based on current report state.

    Logic:
    - Analysts with reports = completed
    - First analyst without report = in_progress
    - Remaining analysts without reports = pending
    - When all analysts done, set Bull Researcher to in_progress
    """
    selected = message_buffer.selected_analysts
    found_active = False

    for analyst_key in ANALYST_ORDER:
        if analyst_key not in selected:
            continue

        agent_name = ANALYST_AGENT_NAMES[analyst_key]
        report_key = ANALYST_REPORT_MAP[analyst_key]
        has_report = bool(chunk.get(report_key))

        if has_report:
            message_buffer.update_agent_status(agent_name, "completed")
            message_buffer.update_report_section(report_key, chunk[report_key])
        elif not found_active:
            message_buffer.update_agent_status(agent_name, "in_progress")
            found_active = True
        else:
            message_buffer.update_agent_status(agent_name, "pending")

    # When all analysts complete, transition research team to in_progress
    if (
        not found_active
        and selected
        and message_buffer.agent_status.get("Bull Researcher") == "pending"
    ):
        message_buffer.update_agent_status("Bull Researcher", "in_progress")


def extract_content_string(content: object) -> str | None:
    """Extract string content from various message formats.
    Returns None if no meaningful text content is found.
    """

    def is_empty(val: object) -> bool:
        """Check if value is empty using Python's truthiness."""
        if val is None or val == "":
            return True
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return True
            try:
                return not bool(ast.literal_eval(s))
            except (ValueError, SyntaxError):
                return False  # Can't parse = real text
        return not bool(val)

    if is_empty(content):
        return None

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, dict):
        text = content.get("text", "")
        return text.strip() if not is_empty(text) else None

    if isinstance(content, list):
        text_parts = [
            item.get("text", "").strip()
            if isinstance(item, dict) and item.get("type") == "text"
            else (item.strip() if isinstance(item, str) else "")
            for item in content
        ]
        result = " ".join(t for t in text_parts if t and not is_empty(t))
        return result if result else None

    return str(content).strip() if not is_empty(content) else None


def classify_message_type(message: object) -> tuple[str, str | None]:
    """Classify LangChain message into display type and extract content.

    Returns:
        (type, content) - type is one of: User, Agent, Data, Control
                        - content is extracted string or None
    """
    content = extract_content_string(getattr(message, "content", None))

    if isinstance(message, HumanMessage):
        if content and content.strip() == "Continue":
            return ("Control", content)
        return ("User", content)

    if isinstance(message, ToolMessage):
        return ("Data", content)

    if isinstance(message, AIMessage):
        return ("Agent", content)

    # Fallback for unknown types
    return ("System", content)


def format_tool_args(args: object, max_length: int = 80) -> str:
    """Format tool arguments for terminal display."""
    result = str(args)
    if len(result) > max_length:
        return result[: max_length - 3] + "..."
    return result


def _process_message_chunk(
    chunk: dict[str, Any], layout: Layout, stats_handler: StatsCallbackHandler, start_time: float
) -> None:
    """Process messages from a stream chunk and update the display."""
    if len(chunk["messages"]) > 0:
        last_message = chunk["messages"][-1]
        msg_id = getattr(last_message, "id", None)

        if msg_id != message_buffer.get_last_message_id():
            message_buffer.set_last_message_id(msg_id)
            msg_type, content = classify_message_type(last_message)
            if content and content.strip():
                message_buffer.add_message(msg_type, content)

            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                for tool_call in last_message.tool_calls:
                    if isinstance(tool_call, dict):
                        message_buffer.add_tool_call(tool_call["name"], tool_call["args"])
                    else:
                        message_buffer.add_tool_call(tool_call.name, tool_call.args)


def _process_debate_chunk(chunk: dict[str, Any]) -> None:
    """Process investment_debate_state updates from a stream chunk."""
    if not chunk.get("investment_debate_state"):
        return
    debate_state = chunk["investment_debate_state"]
    bull_hist = debate_state.get("bull_history", "").strip()
    bear_hist = debate_state.get("bear_history", "").strip()
    judge = debate_state.get("judge_decision", "").strip()

    if bull_hist or bear_hist:
        update_research_team_status("in_progress")
    if bull_hist:
        message_buffer.update_report_section(
            "investment_plan", f"### Bull Researcher Analysis\n{bull_hist}"
        )
    if bear_hist:
        message_buffer.update_report_section(
            "investment_plan", f"### Bear Researcher Analysis\n{bear_hist}"
        )
    if judge:
        message_buffer.update_report_section(
            "investment_plan", f"### Research Manager Decision\n{judge}"
        )
        update_research_team_status("completed")
        message_buffer.update_agent_status("Trader", "in_progress")


def _process_risk_chunk(chunk: dict[str, Any]) -> None:
    """Process risk_debate_state updates from a stream chunk."""
    if not chunk.get("risk_debate_state"):
        return
    risk_state = chunk["risk_debate_state"]
    agg_hist = risk_state.get("aggressive_history", "").strip()
    con_hist = risk_state.get("conservative_history", "").strip()
    neu_hist = risk_state.get("neutral_history", "").strip()
    judge = risk_state.get("judge_decision", "").strip()

    if agg_hist:
        if message_buffer.agent_status.get("Aggressive Analyst") != "completed":
            message_buffer.update_agent_status("Aggressive Analyst", "in_progress")
        message_buffer.update_report_section(
            "final_trade_decision", f"### Aggressive Analyst Analysis\n{agg_hist}"
        )
    if con_hist:
        if message_buffer.agent_status.get("Conservative Analyst") != "completed":
            message_buffer.update_agent_status("Conservative Analyst", "in_progress")
        message_buffer.update_report_section(
            "final_trade_decision", f"### Conservative Analyst Analysis\n{con_hist}"
        )
    if neu_hist:
        if message_buffer.agent_status.get("Neutral Analyst") != "completed":
            message_buffer.update_agent_status("Neutral Analyst", "in_progress")
        message_buffer.update_report_section(
            "final_trade_decision", f"### Neutral Analyst Analysis\n{neu_hist}"
        )
    if judge and message_buffer.agent_status.get("Portfolio Manager") != "completed":
        message_buffer.update_agent_status("Portfolio Manager", "in_progress")
        message_buffer.update_report_section(
            "final_trade_decision", f"### Portfolio Manager Decision\n{judge}"
        )
        message_buffer.update_agent_status("Aggressive Analyst", "completed")
        message_buffer.update_agent_status("Conservative Analyst", "completed")
        message_buffer.update_agent_status("Neutral Analyst", "completed")
        message_buffer.update_agent_status("Portfolio Manager", "completed")


def run_analysis() -> None:
    """Run interactive trading agent analysis."""
    selections = get_user_selections()

    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = selections["research_depth"]
    config["max_risk_discuss_rounds"] = selections["research_depth"]
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    config["google_thinking_level"] = selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = selections.get("openai_reasoning_effort")

    stats_handler = StatsCallbackHandler()
    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]

    graph = TradingAgentsGraph(
        selected_analyst_keys, config=config, debug=True, callbacks=[stats_handler]
    )
    message_buffer.init_for_analysis(selected_analyst_keys)
    start_time = time.time()

    results_dir = Path(config["results_dir"]) / selections["ticker"] / selections["analysis_date"]
    results_dir.mkdir(parents=True, exist_ok=True)
    report_dir = results_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / "message_tool.log"
    log_file.touch(exist_ok=True)

    def _on_message_logged(timestamp: str, message_type: str, content: str) -> None:
        sanitized = content.replace("\n", " ")
        with open(log_file, "a") as f:
            f.write(f"{timestamp} [{message_type}] {sanitized}\n")

    def _on_tool_call_logged(timestamp: str, tool_name: str, args: object) -> None:
        args_str = (
            ", ".join(f"{k}={v}" for k, v in args.items()) if isinstance(args, dict) else str(args)
        )
        with open(log_file, "a") as f:
            f.write(f"{timestamp} [Tool Call] {tool_name}({args_str})\n")

    def _on_report_section_saved(section_name: str, content: str | None) -> None:
        if content:
            file_name = f"{section_name}.md"
            with open(report_dir / file_name, "w") as f:
                f.write(content)

    message_buffer.on_add_message = _on_message_logged
    message_buffer.on_add_tool_call = _on_tool_call_logged
    message_buffer.on_update_report_section = _on_report_section_saved

    layout = create_layout()
    with Live(layout, refresh_per_second=4):
        _run_live_analysis(graph, selections, layout, stats_handler, start_time)

    _post_analysis_prompts(graph, selections)


def _run_live_analysis(
    graph: TradingAgentsGraph,
    selections: dict[str, Any],
    layout: Layout,
    stats_handler: StatsCallbackHandler,
    start_time: float,
) -> None:
    """Run the streaming analysis inside a Rich Live context."""
    update_display(layout, stats_handler=stats_handler, start_time=start_time)

    message_buffer.add_message("System", f"Selected ticker: {selections['ticker']}")
    message_buffer.add_message("System", f"Analysis date: {selections['analysis_date']}")
    message_buffer.add_message(
        "System",
        f"Selected analysts: {', '.join(analyst.value for analyst in selections['analysts'])}",
    )
    update_display(layout, stats_handler=stats_handler, start_time=start_time)

    first_analyst = f"{selections['analysts'][0].value.capitalize()} Analyst"
    message_buffer.update_agent_status(first_analyst, "in_progress")
    update_display(layout, stats_handler=stats_handler, start_time=start_time)

    spinner_text = f"Analyzing {selections['ticker']} on {selections['analysis_date']}..."
    update_display(layout, spinner_text, stats_handler=stats_handler, start_time=start_time)

    init_agent_state = graph.propagator.create_initial_state(
        selections["ticker"], selections["analysis_date"]
    )
    args = graph.propagator.get_graph_args(callbacks=[stats_handler])

    trace: list[dict[str, Any]] = []
    for chunk in graph.graph.stream(init_agent_state, **args):
        _process_message_chunk(chunk, layout, stats_handler, start_time)
        update_analyst_statuses(message_buffer, chunk)
        _process_debate_chunk(chunk)

        if chunk.get("trader_investment_plan"):
            message_buffer.update_report_section(
                "trader_investment_plan", chunk["trader_investment_plan"]
            )
            if message_buffer.agent_status.get("Trader") != "completed":
                message_buffer.update_agent_status("Trader", "completed")
                message_buffer.update_agent_status("Aggressive Analyst", "in_progress")

        _process_risk_chunk(chunk)
        update_display(layout, stats_handler=stats_handler, start_time=start_time)
        trace.append(chunk)

    final_state = trace[-1]
    graph.process_signal(final_state["final_trade_decision"])
    graph.curr_state = final_state

    for agent in message_buffer.agent_status:
        message_buffer.update_agent_status(agent, "completed")

    message_buffer.add_message("System", f"Completed analysis for {selections['analysis_date']}")
    for section in message_buffer.report_sections:
        if section in final_state:
            message_buffer.update_report_section(section, final_state[section])

    update_display(layout, stats_handler=stats_handler, start_time=start_time)


def _post_analysis_prompts(graph: TradingAgentsGraph, selections: dict[str, Any]) -> None:
    """Handle post-analysis save/display prompts outside the Live context."""
    if not graph.curr_state:
        return
    final_state = graph.curr_state

    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")

    save_choice = typer.prompt("Save report?", default="Y").strip().upper()
    if save_choice in ("Y", "YES", ""):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = Path.cwd() / "reports" / f"{selections['ticker']}_{timestamp}"
        save_path_str = typer.prompt(
            "Save path (press Enter for default)", default=str(default_path)
        ).strip()
        save_path = Path(save_path_str)
        try:
            report_file = save_report_to_disk(final_state, selections["ticker"], save_path)
            console.print(f"\n[green]✓ Report saved to:[/green] {save_path.resolve()}")
            console.print(f"  [dim]Complete report:[/dim] {report_file.name}")
        except Exception as e:
            console.print(f"[red]Error saving report: {e}[/red]")

    display_choice = typer.prompt("\nDisplay full report on screen?", default="Y").strip().upper()
    if display_choice in ("Y", "YES", ""):
        display_complete_report(final_state)


@app.command()
def analyze() -> None:
    run_analysis()


if __name__ == "__main__":
    app()
