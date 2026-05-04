"""Command-line entry point for the TradingAgents framework.

Two subcommands are exposed via `fire`:

* ``tradingagents cli [--flag=value ...]`` runs a single non-interactive
  trading-graph pass. Every field of :class:`TradingAgentsConfig`, plus the
  graph-level ticker / trade date / debug / selected analysts options, is
  available as a flag with the previous developer-script values as defaults.

* ``tradingagents tui`` launches the questionary-based interactive runner in
  :mod:`tradingagents.interface.tui`.

Calling ``uv run tradingagents`` with no arguments prints the available
subcommands, courtesy of fire's auto-generated help.
"""

from pathlib import Path
import datetime

import fire

from tradingagents.llm import LLMProvider, ReasoningEffort
from tradingagents.config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph

from .tui import run_tui
from .display import console, print_header, print_summary, print_decision

DEFAULT_TICKER: str = "2330"
DEFAULT_LLM_PROVIDER: LLMProvider = "google_genai"
DEFAULT_DEEP_THINK_LLM: str = "gemini-3.1-pro-preview"
DEFAULT_QUICK_THINK_LLM: str = "gemini-3-flash-preview"
DEFAULT_REASONING_EFFORT: ReasoningEffort = "high"
DEFAULT_RESPONSE_LANGUAGE: str = "zh-TW"
DEFAULT_MAX_DEBATE_ROUNDS: int = 10
DEFAULT_MAX_RISK_DISCUSS_ROUNDS: int = 10
DEFAULT_MAX_RECUR_LIMIT: int = 100
DEFAULT_RESULTS_DIR: str = "./results"
DEFAULT_SELECTED_ANALYSTS: tuple[str, ...] = ("market", "social", "news", "fundamentals")
DEFAULT_DEBUG: bool = True


def _normalize_analysts(value: object) -> list[str]:
    """Coerce a user-supplied analysts value into a list of strings.

    fire passes ``--selected-analysts`` as either a list (if comma-separated
    or square-bracketed) or a tuple, so we accept both and fall back to a
    single-string treatment.

    Args:
        value (object): Raw value from fire (str, list, or tuple).

    Returns:
        list[str]: Normalized analyst keys.
    """
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def _summary_rows(
    *,
    ticker: str,
    trade_date: str,
    config: TradingAgentsConfig,
    selected_analysts: list[str],
    debug: bool,
) -> list[tuple[str, str]]:
    """Build a summary table for the run banner.

    Args:
        ticker (str): The stock ticker.
        trade_date (str): The trade date (``YYYY-MM-DD``).
        config (TradingAgentsConfig): The fully constructed config.
        selected_analysts (list[str]): Analyst keys included in this run.
        debug (bool): Whether debug streaming is enabled.

    Returns:
        list[tuple[str, str]]: ``(field, value)`` pairs for ``print_summary``.
    """
    return [
        ("ticker", ticker),
        ("trade_date", trade_date),
        ("llm_provider", config.llm_provider),
        ("deep_think_llm", config.deep_think_llm),
        ("quick_think_llm", config.quick_think_llm),
        ("reasoning_effort", config.reasoning_effort),
        ("response_language", config.response_language),
        ("selected_analysts", ", ".join(selected_analysts)),
        ("max_debate_rounds", str(config.max_debate_rounds)),
        ("max_risk_discuss_rounds", str(config.max_risk_discuss_rounds)),
        ("max_recur_limit", str(config.max_recur_limit)),
        ("results_dir", str(config.results_dir)),
        ("debug", str(debug)),
    ]


class TradingAgentsCLI:
    """fire-exposed subcommand surface for `tradingagents`."""

    def cli(  # noqa: PLR0913
        self,
        ticker: str = DEFAULT_TICKER,
        trade_date: str | None = None,
        llm_provider: LLMProvider = DEFAULT_LLM_PROVIDER,
        deep_think_llm: str = DEFAULT_DEEP_THINK_LLM,
        quick_think_llm: str = DEFAULT_QUICK_THINK_LLM,
        reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
        response_language: str = DEFAULT_RESPONSE_LANGUAGE,
        max_debate_rounds: int = DEFAULT_MAX_DEBATE_ROUNDS,
        max_risk_discuss_rounds: int = DEFAULT_MAX_RISK_DISCUSS_ROUNDS,
        max_recur_limit: int = DEFAULT_MAX_RECUR_LIMIT,
        results_dir: str = DEFAULT_RESULTS_DIR,
        selected_analysts: object = DEFAULT_SELECTED_ANALYSTS,
        debug: bool = DEFAULT_DEBUG,
    ) -> str:
        """Run a single non-interactive TradingAgents pass.

        All flags default to the values previously hard-coded in the
        developer script; only the ones a user wants to override need to be
        supplied on the command line.

        Args:
            ticker (str, optional): Stock ticker or company name to analyse.
                Defaults to ``"2330"``.
            trade_date (str | None, optional): Trade date in ``YYYY-MM-DD``
                form. Defaults to today when omitted.
            llm_provider (LLMProvider, optional): LangChain provider key
                shared by both LLM tiers. Defaults to ``"google_genai"``.
            deep_think_llm (str, optional): Model name for deep-thinking nodes
                (Research / Risk Manager). Defaults to
                ``"gemini-3.1-pro-preview"``.
            quick_think_llm (str, optional): Model name for quick-thinking
                nodes (analysts, debators). Defaults to
                ``"gemini-3-flash-preview"``.
            reasoning_effort (ReasoningEffort, optional): Unified reasoning
                effort level. Defaults to ``"high"``.
            response_language (str, optional): Language instruction appended
                to every prompt. Defaults to ``"zh-TW"``.
            max_debate_rounds (int, optional): Bull/Bear debate cap. Defaults
                to 10.
            max_risk_discuss_rounds (int, optional): Risk debate cap.
                Defaults to 10.
            max_recur_limit (int, optional): LangGraph recursion limit.
                Defaults to 100.
            results_dir (str, optional): Directory to write logs and caches.
                Defaults to ``"./results"``.
            selected_analysts (object, optional): Analyst keys; accepts a
                comma-separated string, a list, or a tuple. Defaults to all
                four analysts.
            debug (bool, optional): Stream every LangGraph message via the
                Rich pretty-printer. Defaults to True.

        Returns:
            str: The final BUY/SELL/HOLD decision string.
        """
        analysts = _normalize_analysts(selected_analysts)
        td = trade_date or datetime.date.today().strftime("%Y-%m-%d")

        config = TradingAgentsConfig(
            results_dir=Path(results_dir),
            llm_provider=llm_provider,
            deep_think_llm=deep_think_llm,
            quick_think_llm=quick_think_llm,
            reasoning_effort=reasoning_effort,
            response_language=response_language,
            max_debate_rounds=max_debate_rounds,
            max_risk_discuss_rounds=max_risk_discuss_rounds,
            max_recur_limit=max_recur_limit,
        )
        ta = TradingAgentsGraph(selected_analysts=analysts, debug=debug, config=config)

        print_header("TradingAgents · CLI", f"Analysing {ticker} on {td}")
        print_summary(
            _summary_rows(
                ticker=ticker,
                trade_date=td,
                config=config,
                selected_analysts=analysts,
                debug=debug,
            ),
            title="Run configuration",
        )

        _, decision = ta.propagate(ticker, td)
        print_decision(ticker, td, decision)
        return decision

    def tui(self) -> str:
        """Launch the interactive questionary-based TUI.

        Returns:
            str: The final BUY/SELL/HOLD decision string, or empty string if
            the user cancels at the confirmation step.
        """
        return run_tui()


def main() -> None:
    """Fire entry point invoked by the ``tradingagents`` console script."""
    try:
        fire.Fire(TradingAgentsCLI)
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted by user.[/yellow]")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
