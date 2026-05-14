"""Flag-driven CLI entrypoint for the TradingAgents backtest harness.

Exposes :func:`run_backtest` as the ``backtest`` subcommand of the
``tradingagents`` console script. Mirrors :func:`run_cli` for the LLM /
debate / risk-round flags so a backtest reuses the same
:class:`TradingAgentsConfig` knobs the live CLI exposes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path

from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.console import Console

from tradingagents.llm import LLMProvider, ReasoningEffort  # noqa: TC001
from tradingagents.config import ResponseLanguage, TradingAgentsConfig
from tradingagents.backtest import Backtester, BacktestConfig

if TYPE_CHECKING:
    from tradingagents.backtest import BacktestReport


def _split_tickers(value: str | list[str] | tuple[str, ...]) -> list[str]:
    """Split a fire-friendly ``--tickers`` argument into a clean list."""
    items = list(value) if isinstance(value, (list, tuple)) else str(value).split(",")
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        raise ValueError("--tickers must contain at least one symbol.")
    return cleaned


def _print_report(console: Console, report: BacktestReport) -> None:
    """Render the aggregate report and the per-trade table."""
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold cyan", justify="right")
    summary.add_column()
    summary.add_row("Trades", str(len(report.trades)))
    summary.add_row("Buy / Sell / Hold", f"{report.n_buy} / {report.n_sell} / {report.n_hold}")
    summary.add_row(
        "Hit rate", f"{report.hit_rate:.2%}" if report.hit_rate == report.hit_rate else "n/a"
    )
    summary.add_row(
        "Sharpe (annualised)", f"{report.sharpe:.4f}" if report.sharpe == report.sharpe else "n/a"
    )
    summary.add_row("Expectancy", f"{report.expectancy:+.4f}")
    summary.add_row("Avg trade return", f"{report.avg_trade_return:+.4f}")
    summary.add_row("Total compounded return", f"{report.total_return:+.4f}")
    summary.add_row("Worst drawdown", f"{report.worst_drawdown:+.4f}")
    summary.add_row("Estimated LLM cost (USD)", f"{report.estimated_cost_usd:.4f}")
    console.print(
        Panel(
            summary,
            title="[bold magenta]Backtest Summary[/]",
            title_align="left",
            border_style="magenta",
        )
    )

    if not report.trades:
        console.print(Text("No trades recorded.", style="dim italic"))
        return

    table = Table(title="Trades", title_style="bold cyan", header_style="bold")
    table.add_column("Date", no_wrap=True)
    table.add_column("Ticker", no_wrap=True)
    table.add_column("Signal", no_wrap=True)
    table.add_column("Size", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Exit", justify="right")
    table.add_column("Return", justify="right")
    table.add_column("Notes")
    for trade in report.trades:
        signal_style = {"BUY": "bold green", "SELL": "bold red", "HOLD": "bold yellow"}.get(
            trade.recommendation.signal, "bold"
        )
        table.add_row(
            trade.decision_date,
            trade.ticker,
            Text(trade.recommendation.signal, style=signal_style),
            f"{trade.recommendation.size_fraction:.2f}",
            f"{trade.entry_price:.2f}" if trade.entry_price is not None else "-",
            f"{trade.exit_price:.2f}" if trade.exit_price is not None else "-",
            f"{trade.realised_return:+.4f}",
            trade.notes,
        )
    console.print(table)


def run_backtest(  # noqa: PLR0913, D417 -- mirrors run_cli's full flag surface
    tickers: str | list[str] | tuple[str, ...] = "GOOG",
    start: str | None = None,
    end: str | None = None,
    frequency: str = "weekly",
    horizon_days: int = 5,
    initial_cash: float = 100_000.0,
    max_position_fraction: float = 0.2,
    budget_cap_usd: float | None = None,
    dry_run: bool = False,
    reflect_after_each_trade: bool = True,
    output: str | None = None,
    llm_provider: LLMProvider = "google_genai",
    deep_think_llm: str = "gemini-flash-latest",
    quick_think_llm: str = "gemini-flash-latest",
    reasoning_effort: ReasoningEffort = "low",
    response_language: ResponseLanguage = "en-US",
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
    max_recur_limit: int = 40,
) -> BacktestReport:
    """Run a backtest grid and print a Rich-formatted report.

    Args:
        tickers: Comma-separated ticker symbols (or list / tuple via fire).
            Each is evaluated independently against the same date grid.
        start: Inclusive grid start date in YYYY-MM-DD format. Required.
        end: Inclusive grid end date in YYYY-MM-DD format. Required.
        frequency: ``daily`` (every business day) or ``weekly`` (Fridays).
            Defaults to ``weekly`` since per-day LLM cost adds up fast.
        horizon_days: Trading bars forward to mark-to-market each decision.
        initial_cash: Notional capital used only for drawdown framing.
        max_position_fraction: Upper bound applied to the LLM-provided
            size_fraction before scoring; safer than trusting size=1.0.
        budget_cap_usd: Halt the run once estimated LLM spend exceeds
            this many USD. None disables enforcement.
        dry_run: When True the harness swaps :class:`StubChatModel` in
            for every LLM call so the grid runs in seconds and burns no
            API budget.
        reflect_after_each_trade: When True, feeds realised returns
            through :meth:`TradingAgentsGraph.reflect_and_remember` so
            memory updates as the backtest progresses (production-like).
        output: Optional path to write the JSON report dump to. The Rich
            summary is always printed regardless.
        llm_provider / deep_think_llm / quick_think_llm /
            reasoning_effort / response_language / max_debate_rounds /
            max_risk_discuss_rounds / max_recur_limit: standard
            :class:`TradingAgentsConfig` knobs, defaults tuned for cheap
            iteration (gemini-flash, 1 debate round each, low effort).

    Returns:
        BacktestReport: The aggregate metrics. The same object is also
        rendered to the console; pass ``output`` to additionally write
        ``model_dump_json`` to disk.
    """
    if start is None or end is None:
        raise ValueError("--start and --end are required (YYYY-MM-DD).")

    ticker_list = _split_tickers(tickers)
    if frequency not in {"daily", "weekly"}:
        raise ValueError(f"frequency must be 'daily' or 'weekly', got {frequency!r}.")

    trading_config = TradingAgentsConfig(
        llm_provider=llm_provider,
        deep_think_llm=deep_think_llm,
        quick_think_llm=quick_think_llm,
        max_debate_rounds=max_debate_rounds,
        max_risk_discuss_rounds=max_risk_discuss_rounds,
        max_recur_limit=max_recur_limit,
        reasoning_effort=reasoning_effort,
        response_language=response_language,
    )
    backtest_config = BacktestConfig(
        tickers=ticker_list,
        start_date=start,
        end_date=end,
        frequency=frequency,
        horizon_days=horizon_days,
        initial_cash=initial_cash,
        max_position_fraction=max_position_fraction,
        budget_cap_usd=budget_cap_usd,
        dry_run=dry_run,
        reflect_after_each_trade=reflect_after_each_trade,
        trading_config=trading_config,
    )

    console = Console()
    console.print(
        Panel(
            (
                f"Tickers: [bold]{', '.join(ticker_list)}[/]\n"
                f"Window:  [bold]{start} -> {end}[/]\n"
                f"Frequency: [bold]{frequency}[/], horizon: [bold]{horizon_days}d[/]\n"
                f"Dry run: [bold]{dry_run}[/], reflect: [bold]{reflect_after_each_trade}[/]\n"
                f"Budget cap: [bold]{budget_cap_usd}[/]"
            ),
            title="[bold blue]TradingAgents Backtest[/]",
            title_align="left",
            border_style="blue",
        )
    )

    report = Backtester(config=backtest_config).run(
        on_trade=lambda trade: console.print(
            f"  - {trade.decision_date} {trade.ticker} {trade.recommendation.signal} "
            f"size={trade.recommendation.size_fraction:.2f} "
            f"return={trade.realised_return:+.4f}"
        )
    )

    _print_report(console, report)

    if output:
        Path(output).write_text(report.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]Report JSON written to[/] {output}")

    return report
