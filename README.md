<div align="center" markdown="1">

# TradingAgents

[![PyPI version](https://img.shields.io/pypi/v/tradingagents.svg)](https://pypi.org/project/tradingagents/)
[![python](https://img.shields.io/badge/-Python_%7C_3.12%7C_3.13%7C_3.14-blue?logo=python&logoColor=white)](https://www.python.org/downloads/source/)
[![uv](https://img.shields.io/badge/-uv_dependency_management-2C5F2D?logo=python&logoColor=white)](https://docs.astral.sh/uv/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Pydantic v2](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json)](https://docs.pydantic.dev/latest/contributing/#badges)
[![tests](https://github.com/Mai0313/TradingAgents/actions/workflows/test.yml/badge.svg)](https://github.com/Mai0313/TradingAgents/actions/workflows/test.yml)
[![code-quality](https://github.com/Mai0313/TradingAgents/actions/workflows/code-quality-check.yml/badge.svg)](https://github.com/Mai0313/TradingAgents/actions/workflows/code-quality-check.yml)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Mai0313/TradingAgents)
[![license](https://img.shields.io/badge/License-MIT-green.svg?labelColor=gray)](https://github.com/Mai0313/TradingAgents/tree/main?tab=License-1-ov-file)
[![PRs](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/Mai0313/TradingAgents/pulls)
[![contributors](https://img.shields.io/github/contributors/Mai0313/TradingAgents.svg)](https://github.com/Mai0313/TradingAgents/graphs/contributors)

</div>

🚀 **TradingAgents** is a multi-agent LLM financial trading framework that leverages large language models to simulate analyst teams, research debates, and portfolio management decisions for stock trading analysis.

Other Languages: [English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

## ✨ Highlights

- Built on **LangGraph** for robust multi-agent orchestration
- Multi-agent architecture: Analyst Team → **Situation Summariser** → Research Team → Trader → Risk Management → Portfolio Management
- **Structured trade recommendation** — the Risk Judge emits a typed `TradeRecommendation` (signal, size, target, stop, horizon, confidence, rationale) parsed from a JSON block plus the canonical `FINAL TRANSACTION PROPOSAL` line
- **Backtest harness** — `tradingagents backtest` drives `propagate()` across a date grid, scores realised returns from cached OHLCV, reports Sharpe / hit-rate / drawdown, and supports a `--dry-run` stub-LLM mode for harness validation
- Powered by `langchain.chat_models.init_chat_model`; supports any provider keyed via an explicit `llm_provider` field plus a model name (OpenAI, Anthropic, Google Gemini, xAI (Grok), OpenRouter, Ollama, HuggingFace, LiteLLM)
- Unified `reasoning_effort` knob (`low / medium / high / xhigh / max`) mapped per provider to native parameters (Anthropic `effort`, OpenAI `reasoning_effort`, Google `thinking_level`)
- Market data powered by `yfinance` for OHLCV, fundamentals, technical indicators, news, insider transactions, analyst ratings, earnings calendar, institutional holders, short interest, dividends / splits, and regional macro context (local index, ^TNX, ^VIX)
- Locale-aware Google News routing — exchange suffix (`.TW`, `.HK`, `.T`, `.DE`, ...) selects the right `hl` / `gl` / `ceid` so non-US issuers get local-language coverage
- Point-in-time-safe data fetchers — every historical tool filters by a reporting-lag-adjusted `as_of` date so back-tests cannot leak future filings
- Pydantic-based configuration with strict typing and validation
- Analysis results automatically saved to `results/` with organized subfolders (versioned state-log schema with built-in v1 → v2 migration for the reflect CLI)
- Modern `src/` layout with full type-annotated code
- Fast dependency management via `uv`
- Pre-commit suite: ruff, mdformat, codespell, mypy, uv hooks
- Pytest with coverage; MkDocs Material documentation

## 🚀 Quick Start

```bash
git clone https://github.com/Mai0313/TradingAgents.git
cd TradingAgents
make uv-install               # Install uv (only needed once)
uv sync                       # Install dependencies
cp .env.example .env          # Configure your API keys
```

### Configure API Keys

Edit `.env` and set your LLM provider keys:

```bash
# LLM Providers (set the one you use)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
XAI_API_KEY=...
OPENROUTER_API_KEY=...
```

### Usage

#### Command line / interactive

The package ships a `tradingagents` console script with four subcommands:

```bash
uv run tradingagents tui                     # interactive questionary prompts
uv run tradingagents cli                     # run with all defaults
uv run tradingagents cli --ticker AAPL \
    --deep_think_llm gpt-5 \
    --quick_think_llm gpt-5-mini             # override flags
uv run tradingagents reflect --ticker AAPL --date 2024-05-10 --returns 0.032   # post-trade reflection
uv run tradingagents backtest --tickers GOOG,2330.TW \
    --start 2024-01-01 --end 2024-06-30 \
    --frequency weekly --horizon-days 5 \
    --budget-cap-usd 25                      # grid backtest with LLM cost cap
uv run tradingagents backtest --tickers GOOG \
    --start 2024-01-01 --end 2024-06-30 --dry-run   # validate the harness in seconds, $0 cost
uv run tradingagents --help                  # rich-rendered top-level help
uv run tradingagents cli --help              # rich-rendered per-command flags
```

`tradingagents tui` walks you through every parameter (ticker, date, provider, models, debate rounds, analyst selection, ...) via interactive prompts; `tradingagents cli` is the same flow but driven entirely by command-line flags so it composes with shell scripts and CI. `tradingagents reflect` re-runs the post-trade reflector against a previously-recorded state log and appends lessons to the BM25 memories. `tradingagents backtest` iterates `propagate()` over a date grid, marks each decision to market against the next-bar close, reports Sharpe / hit rate / expectancy / drawdown, and enforces a `--budget-cap-usd` based on token-aware cost tracking. Add `--dry-run` to swap in an in-memory stub LLM that produces canned `TradeRecommendation` payloads — useful for validating the harness against real cached OHLCV without burning API budget. Both interactive routes stream LangGraph agent messages through Rich panels (Markdown for prose, JSON-pretty for tool output, truncated when payloads exceed a screenful). `python -m tradingagents <subcommand>` works as well.

#### Programmatic

```python
from tradingagents.config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = TradingAgentsConfig(
    llm_provider="openai",
    deep_think_llm="gpt-5",
    quick_think_llm="gpt-5-mini",
    max_debate_rounds=1,
    max_risk_discuss_rounds=1,
    max_recur_limit=100,
    reasoning_effort="medium",
    response_language="en-US",
)

ta = TradingAgentsGraph(debug=True, config=config)
state, recommendation = ta.propagate("NVDA", "2024-05-10")
print(recommendation.signal, recommendation.size_fraction, recommendation.confidence)
print(recommendation.rationale)
```

`propagate()` returns `(AgentState, TradeRecommendation)`. `TradeRecommendation` is a Pydantic model with:

- `signal: Literal["BUY", "SELL", "HOLD"]` — the canonical direction
- `size_fraction: float` (0.0 – 1.0) — position size as a fraction of available capital
- `target_price: float | None`, `stop_loss: float | None`, `time_horizon_days: int | None` — trade plan
- `confidence: float` (0.0 – 1.0), `rationale: str`, `warning_message: str | None` (set when the parser falls back)

The structured form is also persisted to `AgentState.final_trade_recommendation` and the state log JSON, so the `reflect` and `backtest` subcommands can rebuild it later.

`response_language` is a BCP 47 tag from the `ResponseLanguage` `Literal` (`zh-TW`, `zh-CN`, `en-US`, `ja-JP`, `ko-KR`, `de-DE`); pick the closest one to the language you want the agents to reason in.

`TradingAgentsGraph.propagate` also accepts an optional `on_message` callback (`Callable[[AnyMessage], None]`) that fires once per streamed LangGraph message — useful for plugging in your own renderer; the bundled CLI / TUI use this hook to drive the Rich panels.

`llm_provider` is one of the `langchain.chat_models.init_chat_model` registry keys (`openai`, `anthropic`, `google_genai`, `xai`, `openrouter`, `ollama`, `huggingface`, `litellm`); `deep_think_llm` / `quick_think_llm` take the model name as accepted by that provider (`gpt-5`, `claude-sonnet-4-6`, `gemini-3-pro-preview`, `grok-4`, ...).

`max_recur_limit` must be at least **30** — the Situation Summariser node introduced in the P0 rollout adds one superstep to the graph, so the previous floor of 25 is no longer enough for the minimum-round topology. The default in the CLI / TUI is 100.

Set `response_language` to control the language requested in all agent prompts. Tickers without exchange suffixes are resolved automatically with Yahoo Finance Search. For Taiwan stocks, pass the numeric stock code directly, such as `2330`, `2408`, or `8069`; explicit Yahoo Finance symbols such as `2330.TW`, `8069.TWO`, `AAPL`, and `TSM` are also supported.

```python
config = TradingAgentsConfig(
    llm_provider="openai",
    deep_think_llm="gpt-5",
    quick_think_llm="gpt-5-mini",
    max_debate_rounds=1,
    max_risk_discuss_rounds=1,
    max_recur_limit=100,
    response_language="zh-TW",
)

ta = TradingAgentsGraph(config=config)
state, recommendation = ta.propagate("2330", "2024-05-10")
```

#### Backtest

The same `propagate()` flow can be driven over a date grid via the `Backtester` Pydantic model (or the `tradingagents backtest` CLI shown above):

```python
from tradingagents.backtest import BacktestConfig, Backtester

cfg = BacktestConfig(
    tickers=["GOOG", "2330.TW"],
    start_date="2024-01-01",
    end_date="2024-06-30",
    frequency="weekly",  # or "daily"
    horizon_days=5,  # mark-to-market window per decision
    budget_cap_usd=25.0,  # raises CostBudgetExceeded and stops the loop
    reflect_after_each_trade=True,
    trading_config=config,
)
report = Backtester(config=cfg).run()
print(report.sharpe, report.hit_rate, report.estimated_cost_usd)
```

The harness instantiates a fresh `TradingAgentsGraph` per ticker (per-run state is mutable), reuses the same `CostTracker` callback across tickers so the budget cap accumulates, scores each decision against the next-bar OHLCV from the existing 15-year cache, and optionally feeds the realised return through `reflect_and_remember` so memory grows during the backtest just as in production. Pass `dry_run=True` to swap in the in-memory `StubChatModel` for harness validation.

## 📁 Project Structure

```
src/
└── tradingagents/
    ├── agents/           # Agent implementations
    │   ├── analysts/     # Market, News, News-Sentiment, Fundamentals analysts
    │   ├── managers/     # Research & Portfolio managers
    │   ├── preprocessors/# Situation Summariser node (analyst reports → BM25 query)
    │   ├── researchers/  # Bull & Bear researchers
    │   ├── risk_mgmt/    # Risk management agents
    │   ├── trader/       # Trader agent
    │   ├── prompts/      # All agent prompts as .md templates
    │   └── utils/        # Shared agent utilities (memory, tools, state)
    ├── dataflows/        # Data ingestion via yfinance + Google News RSS
    ├── graph/            # LangGraph trading graph setup
    │   ├── trading_graph.py    # Main TradingAgentsGraph orchestrator
    │   ├── signal_processing.py# TradeRecommendation parser + JSON / canonical-line precedence
    │   └── reflection.py       # Post-trade reflector
    ├── interface/        # CLI / TUI / backtest / reflect implementations
    │   ├── cli.py        # fire-driven flag runner (run_cli)
    │   ├── tui/          # textual-based interactive app
    │   ├── backtest.py   # fire-driven backtest runner (run_backtest)
    │   ├── reflect.py    # fire-driven reflect runner (run_reflect)
    │   ├── display.py    # rich-based LangChain message renderer + TradeRecommendation panel
    │   └── help.py       # rich-based replacement for fire's pager help
    ├── backtest.py       # Backtester engine, CostTracker, StubChatModel, BacktestReport
    ├── llm.py            # Chat model construction (init_chat_model wrapper + reasoning_effort mapping)
    ├── config.py         # TradingAgentsConfig schema + global singleton
    ├── __init__.py       # Top-level public API (TradingAgentsConfig, TradingAgentsGraph)
    └── __main__.py       # Console script entry point (fire dispatcher with rich help)
```

## 🤖 Agent Workflow

TradingAgents orchestrates **12 LLM agents** plus **3 supporting components** through a LangGraph `StateGraph`. Every run goes through 4 sequential phases linked by a Situation Summariser, and the state (reports, debate transcripts, trade decisions) is persisted through a Pydantic `AgentState` shared across all nodes.

### Phase 1 — Analyst Team (Data Collection)

By default, four analysts run in sequence; `selected_analysts` can run a subset. Each analyst has its LLM bound to a specific set of `yfinance`-backed `@tool` functions from the central tool registry, and loops with its own `ToolNode` until no more tool calls are emitted. Between analysts a `Msg Clear` node resets the conversation history (emitting `RemoveMessage` + a `HumanMessage("Continue")` placeholder for Anthropic compatibility).

| Analyst                    | LLM-bound tools                                                                                                                                                                   | Writes to state       |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| **Market Analyst**         | `get_stock_data`, `get_indicators`, `get_dividends_splits`                                                                                                                        | `market_report`       |
| **News Sentiment Analyst** | `get_news`                                                                                                                                                                        | `sentiment_report`    |
| **News Analyst**           | `get_news`, `get_global_news`, `get_insider_transactions`, `get_market_context`, `get_earnings_calendar`                                                                          | `news_report`         |
| **Fundamentals Analyst**   | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_analyst_ratings`, `get_institutional_holders`, `get_short_interest`, `get_dividends_splits` | `fundamentals_report` |

All historical tools filter their output by an `as_of` date (reporting-lag-adjusted) so back-tests cannot leak future filings. Tools that have no historical archive in yfinance (`get_institutional_holders`, `get_short_interest`) deliberately return a `[NO_DATA]` sentinel for back-dated `curr_date` instead of silently leaking the current snapshot.

Supported technical indicators (selected by the Market Analyst, **6 – 8 per run**): `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `mfi`, `cci`, `wr`, `kdjk`, `kdjd`, `stochrsi`, `adx`, `pdi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `supertrend`, `supertrend_ub`, `supertrend_lb`, `vwma`, `obv`. The Market Analyst is asked to pick a balanced mix of trend / momentum / volatility / volume signals; an insufficient-data preamble (`DATA WARNING`) is emitted whenever the underlying history has fewer than 50 bars (so long-window indicators are unreliable).

### Phase 1.5 — Situation Summariser

After the last selected analyst's Msg Clear, a single **Situation Summariser** node (quick-thinking LLM) distils the selected analyst reports into a compact ≤400-token structured snapshot. Missing reports from an analyst subset are marked unavailable rather than invented. The summary populates `state.situation_summary` and becomes the BM25 retrieval query for every downstream memory lookup, replacing the previous 10-20 KB `combined_reports` query that was too lexically diffuse to surface relevant past situations.

### Phase 2 — Research Debate

- **Bull Researcher** and **Bear Researcher** debate for `max_debate_rounds` rounds (default: 1 round each), taking turns based on who spoke last. Each researcher retrieves top-k BM25 matches from its own `FinancialSituationMemory` and sees both the past situation snapshot and the lesson learned (not just the lesson string).
- Termination: `count >= 2 * max_debate_rounds` routes the graph to **Research Manager** (deep-thinking LLM), which evaluates the full debate, produces the `investment_plan`, and populates `investment_debate_state.judge_decision`.

### Phase 3 — Trader

**Trader** (quick-thinking LLM) consumes `investment_plan` plus the top-k `trader_memory` matches and produces `trader_investment_plan`. Its output must end with `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`.

### Phase 4 — Risk Control Debate

Three debaters rotate in a fixed order — **Aggressive → Conservative → Neutral → Aggressive → …** — for `max_risk_discuss_rounds` rounds (default: 1 round per stance). Termination: `count >= 3 * max_risk_discuss_rounds` routes to the **Risk Judge** (deep-thinking LLM via `create_risk_manager`), which writes `final_trade_decision`. The Risk Judge prompt requires a fenced ```` ```json ```` block containing the `TradeRecommendation` schema (signal, size_fraction, target_price, stop_loss, time_horizon_days, confidence, rationale, warning_message) plus a canonical `FINAL TRANSACTION PROPOSAL: **<signal>**` line. The deterministic `SignalProcessor` parses both — the canonical line wins on disagreement, and a graceful fallback fills conservative defaults (size 0.5, confidence 0.5) if the JSON block is missing or malformed.

### Supporting components

- **Situation Summariser** — distils analyst reports into the BM25 retrieval query so memory lookups stay lexically tight.
- **FinancialSituationMemory** — BM25Okapi-backed per-agent memory (5 instances: bull, bear, trader, invest_judge, risk_manager). Purely lexical, no external embeddings API required. Each match surfaces both the past situation snapshot and the lesson — agents judge analogy applicability before applying the lesson.
- **Reflector** — After the trade outcome is known, `TradingAgentsGraph.reflect_and_remember(returns_losses)` runs post-trade reflection against each of the 5 memories. The reflector emits a structured rubric (1 – 5 score per factor + overall reasoning + outcome quality + lesson category enum) so the backtest harness can aggregate reasoning trajectory over time.

### Flow Diagram

```
START
  │
  ▼
[Market Analyst ⇄ tools_market] → Msg Clear
  │
  ▼
[News Sentiment Analyst ⇄ tools_social] → Msg Clear
  │
  ▼
[News Analyst ⇄ tools_news] → Msg Clear
  │
  ▼
[Fundamentals Analyst ⇄ tools_fundamentals] → Msg Clear
  │
  ▼
Situation Summariser  →  state.situation_summary
  │
  ▼
[Bull Researcher ⇄ Bear Researcher] × max_debate_rounds
  │
  ▼
Research Manager  →  Trader
                        │
                        ▼
[Aggressive → Conservative → Neutral] × max_risk_discuss_rounds
  │
  ▼
Risk Judge  →  SignalProcessor (TradeRecommendation)  →  END
```

Per-run logs are written under `results/<TICKER>/`: `full_states_log_<TICKER>_<DATE>.json` (v2 schema wrapped under `{"schema_version": 2, "runs": {...}}`), `conversation_log_<TICKER>_<DATE>.txt`, and `conversation_log_<TICKER>_<DATE>.json` (the base path resolves from `TradingAgentsConfig.results_dir`, which defaults to `./results`). The `reflect` CLI transparently migrates v1 logs on read so older runs remain replayable.

## 🤝 Contributing

For development instructions including documentation, testing, and Docker services, please see [CONTRIBUTING.md](CONTRIBUTING.md).

- Open issues/PRs
- Follow the coding style (ruff, type hints)
- Use Conventional Commit messages and descriptive PR titles

## 📄 License

MIT — see `LICENSE`.
