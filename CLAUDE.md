# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependency / environment is managed by `uv` (not pip). Dev extras live under `--group dev`; docs under `--group docs`.

Running the pipeline (the project ships a `tradingagents` console script registered in `[project.scripts]`):

```bash
uv run tradingagents tui                              # interactive textual app
uv run tradingagents cli                              # all defaults (GOOG, today, gemini-3.1-pro-preview)
uv run tradingagents cli --ticker AAPL --date 2024-05-10
uv run tradingagents cli --llm_provider openai --deep_think_llm gpt-5 --quick_think_llm gpt-5-mini
uv run tradingagents reflect --ticker AAPL --date 2024-05-10 --returns 0.032   # post-trade reflection (see Memory section)
uv run tradingagents backtest --tickers GOOG --start 2024-01-01 --end 2024-06-30 \
    --frequency weekly --horizon-days 5 --budget-cap-usd 25                    # grid backtest with cost cap
uv run tradingagents backtest --tickers GOOG --start 2024-01-01 --end 2024-06-30 --dry-run
uv run tradingagents --help                           # rich-rendered top-level help (also `cli --help`)
```

Quality gates:

```bash
make fmt                  # uv run pre-commit run -a (ruff, mypy, codespell, mdformat, gitleaks, uv-sync, ...)
make clean                # nuke caches, dist, docs, .github/reports
make gen-docs             # build MkDocs Material (then `uv run mkdocs serve` on :9987)
```

Tests: a small **mock-based** pytest suite lives under `tests/`. It exercises pure helpers and graph wiring via `monkeypatch` only — **no live LLM or yfinance network calls** — so `make test` / `uv run pytest` is safe and free. Update the existing tests when changing the contracts they pin (error-message format, public function names, no-data sentinels), and feel free to add similarly mock-based tests when you change shared invariants. Do **not** propose tests that require real LLM API or yfinance traffic — each live LangGraph run hits paid LLM APIs and costs real money.

API keys: one of `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `XAI_API_KEY` / `OPENROUTER_API_KEY` is required, picked by `llm_provider`. See `.env.example`.

## Architecture

### One-line summary

A LangGraph `StateGraph` orchestrates 12 LLM agent nodes plus a Situation Summariser preprocessor and per-agent BM25 memories through 4 sequential phases (Analysts → Summariser → Research debate → Trader → Risk debate), driven by a single `TradingAgentsConfig` and exposing both a programmatic API (`TradingAgentsGraph.propagate(ticker, date) -> (AgentState, TradeRecommendation)`) and a fire-driven CLI / TUI / reflect / backtest set of subcommands.

### Big picture flow (`src/tradingagents/graph/setup.py`)

```
START
 → [Market Analyst ⇄ tools_market]   → Msg Clear
 → [News-Sentiment Analyst ⇄ tools_social] → Msg Clear     # internal key still "social"
 → [News Analyst ⇄ tools_news]       → Msg Clear
 → [Fundamentals Analyst ⇄ tools_fundamentals] → Msg Clear
 → Situation Summariser → state.situation_summary
 → [Bull Researcher ⇄ Bear Researcher] × max_debate_rounds
 → Research Manager → Trader
 → [Aggressive → Conservative → Neutral] × max_risk_discuss_rounds
 → Risk Judge → SignalProcessor (TradeRecommendation) → END
```

Each analyst phase is an LLM-with-tools loop terminated by `should_continue_<analyst>` in `graph/conditional_logic.py`. Between analysts a `Msg Clear` node emits `RemoveMessage` for every prior message plus a placeholder `HumanMessage("Continue")` so Anthropic's strict alternating-role validation does not blow up. **Don't remove that placeholder** — it's load-bearing for Anthropic.

The Situation Summariser (`agents/preprocessors/situation_summariser.py`) runs once between the last selected analyst's Msg Clear and the Bull Researcher. It uses the quick-thinking LLM to distil the selected analyst reports into a ≤400-token snapshot stored in `state.situation_summary`; missing reports from an analyst subset must be marked unavailable, not invented. Every downstream memory query uses this snapshot (falling back to `state.combined_reports` when empty) instead of the full multi-KB report concatenation.

### State

`AgentState` (`agents/utils/agent_states.py`) is the single Pydantic model passed through every node. Nested `InvestDebateState` and `RiskDebateState` track the two debate phases. `messages` uses `Annotated[list[AnyMessage], add_messages]` so the LangGraph reducer fires; access fields by attribute (`state.market_report`), never `state["..."]` or `.get(...)`. Node functions return `dict[str, Any]` containing only the keys to update.

### LLMs (`llm.py`)

`build_chat_model(provider, model, *, reasoning_effort, callbacks)` wraps `langchain.chat_models.init_chat_model` and returns a `ChatModel` union (OpenAI/Anthropic/Google/xAI/HuggingFace/OpenRouter/Ollama/LiteLLM). The unified `reasoning_effort` (`low/medium/high/xhigh/max`) is mapped per provider in `_apply_reasoning`:

- `anthropic` → `effort` (native pass-through)
- `openai` → `reasoning_effort` (`max` → `xhigh`)
- `google_genai` → `thinking_level` (`xhigh`/`max` clamped to `high`)
- others ignore it

Any model name containing `gemini` or `google` is force-routed through `NormalizedChatGoogleGenerativeAI`, which flattens Gemini 3's list-shaped `message.content` back to a string so downstream prompt concatenation does not break. Type LLM-bearing fields as `ChatModel` (the union), not `BaseChatModel`. When holding one inside a Pydantic model, annotate `SkipValidation[ChatModel]` to stop LangChain's per-class validators from fighting each other.

### Configuration (`config.py`)

`TradingAgentsConfig` is a Pydantic model with no defaults for `llm_provider` / `deep_think_llm` / `quick_think_llm` / `max_debate_rounds` / `max_risk_discuss_rounds` / `max_recur_limit` (caller must supply). `max_recur_limit` has a `ge=30` floor — the Situation Summariser adds one superstep, so the minimum-round topology no longer fits in 25 steps. `data_cache_dir` is a `@computed_field` under `results_dir`. `set_config()` / `get_config()` use a `ContextVar` so deeply-nested code (e.g. `dataflows/yfinance._get_stock_stats_bulk`, `agents/prompts.__init__._language_instruction`) can read the active config without prop-drilling. `TradingAgentsGraph._setup` (a `model_validator(mode="after")`) registers the active config. **Always construct a config and pass it to `TradingAgentsGraph` first**, otherwise tools / prompts that call `get_config()` raise `RuntimeError`.

### Tools and dataflows

Agent tools (`agents/utils/{core_stock,fundamental_data,news_data,technical_indicators}_tools.py`) are thin `@tool`-decorated wrappers over plain functions in `dataflows/yfinance.py` and `dataflows/news.py`. Tool-to-analyst ownership lives in `agents/utils/tool_registry.py`; both `TradingAgentsGraph.tool_nodes` and analyst `llm.bind_tools(...)` must use that registry:

- **market**: `get_stock_data`, `get_indicators`, `get_dividends_splits`
- **social** (News-Sentiment Analyst): `get_news`
- **news**: `get_news`, `get_global_news`, `get_insider_transactions`, `get_market_context`, `get_earnings_calendar`
- **fundamentals**: `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_analyst_ratings`, `get_institutional_holders`, `get_short_interest`, `get_dividends_splits`

During `TradingAgentsGraph.propagate()`, `runtime.RunContext` records the active ticker, trade date, and response language. Tool wrappers reject any future `curr_date`, `start_date`, or `end_date` with `[TOOL_ERROR]`; do not silently clamp future requests. Historical dataflows still filter their output by an `as_of` date (reporting-lag-adjusted). Tools without a historical archive in yfinance (`get_institutional_holders`, `get_short_interest`, and the recommendation summary inside `get_analyst_ratings`) return a `[NO_DATA]` sentinel for back-dated `curr_date` so back-tests cannot leak present-day positioning. Historical `get_earnings_calendar` must not expose the current-only `yfinance.calendar` snapshot; forward rows keep only date / estimate columns plus a source-limitation note.

Supported technical indicators (Market Analyst is asked to pick **6 – 8 per run**, defined in `BEST_IND_PARAMS` inside `dataflows/yfinance.py`): `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `mfi`, `cci`, `wr`, `kdjk`, `kdjd`, `stochrsi`, `adx`, `pdi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `supertrend`, `supertrend_ub`, `supertrend_lb`, `vwma`, `obv`. `get_stock_stats_indicators_batch` emits a `DATA WARNING` preamble whenever the underlying OHLCV history has fewer than 50 bars.

The 15-year OHLCV cache (`_resolve_history_with_cache`) writes a ticker-only filename (`<TICKER>-YFin-data.csv`); each read validates the cached window covers the inclusive `[curr_date - 15y, curr_date]` range and re-downloads a wider window only on partial coverage. Adjacent run-dates therefore reuse the same on-disk file. Indicator computation must slice cached history to `Date <= curr_date` before `stockstats.wrap(...)` because backtest scoring can legitimately extend the cache past the decision date.

Ticker resolution (`dataflows/tickers.py`): bare symbols are resolved via `yf.Search`; pure-digit symbols also try `<DIGITS>.TW` and `<DIGITS>.TWO` (Taiwan stocks like `2330`, `8069`); explicit suffixed symbols (`AAPL`, `2330.TW`) bypass search. `get_news_locale` maps the resolved suffix to `(hl, gl, ceid)` for the Google News RSS URL, so bare digit Taiwan tickers route to Taiwan locale instead of US defaults. `get_market_context` reuses the same mapping to pick the local index ticker (`^TWII`, `^GSPC`, `^N225`, `^HSI`, ...). `get_news_google_rss` tries `<ticker> stock` first, then a resolved company-name query when ticker-only search has no in-window results. Provider metadata lives in `dataflows/providers.py`; keep future SEC / FRED / vendor integrations behind that adapter boundary instead of wiring paid APIs straight into tools.

### Memory (`agents/utils/memory.py`)

`FinancialSituationMemory` is a Pydantic `BaseModel` using **BM25Okapi** (lexical, no embeddings API). `TradingAgentsGraph` constructs five instances: `bull_memory`, `bear_memory`, `trader_memory`, `invest_judge_memory`, `risk_manager_memory`. Each is wired to `<config.data_cache_dir>/memories/<name>.jsonl`; the file is auto-loaded on construction and atomically rewritten on every `add_situations(...)` call so reflections persist across processes. Memory rows include `situation`, `recommendation`, and `metadata`; legacy two-field rows load with empty metadata. `get_memories(..., min_similarity=0.0)` uses a strict `>` filter, so zero-overlap BM25 matches are not returned. Each researcher / judge renders matches via `format_memories_for_prompt` so the agent sees both the past situation snapshot and the lesson. `Reflector` accepts optional `ReflectionOutcomeContext` (entry / exit / horizon / benchmark returns), stores metadata (`ticker`, `trade_date`, `signal`, `realised_return`, `component`, `prompt_version`), and parses the required rubric into `ReflectionScores` so backtests can aggregate reasoning-quality trends.

After the trade outcome is known, run `tradingagents reflect --ticker X --date Y --returns Z` (or call `TradingAgentsGraph.reflect_and_remember(returns, state=...)` programmatically). The CLI subcommand reads `<results_dir>/<TICKER>/full_states_log_<TICKER>_<DATE>.json`, normalises the payload through `_migrate_state_log_v1_to_v2` when needed, reconstructs the `AgentState`, runs `Reflector` over each component, and appends the lessons to the JSONL files. The reflector grades reasoning quality (decision-process correctness) AND emits a structured rubric — 1 – 5 per macro/technicals/price_action/news_flow/sentiment/fundamentals + overall_reasoning + outcome_quality + a `lesson_category` enum — see `prompts/reflector.md`.

### Prompts (`agents/prompts/`)

Every agent's system / user prompt is a separate `.md` file (e.g. `bull_researcher.md`, `risk_manager.md`, `trader_system.md`, `trader_user.md`, `situation_summariser.md`, `news_sentiment_analyst.md`). Load via `load_prompt(name)` and call `.format(**kwargs)` on the result. **Never inline prompts as Python string literals.** `load_prompt` automatically appends a "Please respond in <BCP47>." line read from the active `TradingAgentsConfig.response_language`, so prompts must use `{{` and `}}` to escape literal braces. The marker `{{require_canonical_signal}}` is replaced before `.format()` with a centralised "keep BUY/SELL/HOLD in English" notice — use it in any prompt whose output is signal-parsed downstream.

Analyst prompts pin deterministic evidence windows: Market OHLCV / indicators use 90 days, news / sentiment use 14 days, dividends / splits use 365 days ending at `current_date`. Analyst nodes use `analyst_report_or_evidence_warning(...)`; if the LLM produces a report before any tool result is observed, write the warning report rather than ungrounded prose. Any node storing `response.content` into state should pass it through `flatten_message_content(...)` so list-shaped provider output is normalized consistently.

### Signal extraction (`graph/signal_processing.py`)

`extract_trade_recommendation(text) -> TradeRecommendation` is the structured-output parser. The Risk Judge prompt requires both a fenced ```` ```json ```` block conforming to `TradeRecommendation` (signal, size_fraction, entry_reference_price, target_price, stop_loss, time_horizon_days, confidence, currency, rationale, warning_message) AND a canonical `FINAL TRANSACTION PROPOSAL: **<signal>**` line. Resolution order: canonical line wins on disagreement; `HOLD` forces `size_fraction=0.0`; missing / malformed JSON falls back to conservative defaults (BUY/SELL size 0.25, HOLD size 0.0, confidence 0.5) with `warning_message` populated. `TradingAgentsGraph.propagate` enriches the parsed recommendation with latest as-of close and fundamentals currency when available. The parser **never raises** — degrading gracefully matters more than blowing up a paid LangGraph run that already has every other agent's output committed.

### Backtest harness (`backtest.py`, `interface/backtest.py`)

`Backtester(config=BacktestConfig(...)).run() -> BacktestReport` iterates `propagate()` across a `(ticker, decision_date)` grid, marks each decision against the next-bar close from the cached OHLCV, applies transaction cost / slippage / shorting rules, and aggregates Sharpe / hit rate / expectancy / worst drawdown. `BacktestReport.benchmarks` includes buy-and-hold, always-HOLD, simple SMA crossover, and deterministic random baselines; it also records chronological train / validation / test `split_reports`, `signal_distribution`, `warning_rate`, `prompt_versions`, and `model_names`. With `walk_forward=True`, the loop is date-major and reflection/memory updates happen only after every ticker for that decision date has been scored, so later tickers cannot see same-date or future outcomes. `CostTracker` is a LangChain `BaseCallbackHandler` that tallies token usage by model name and raises `CostBudgetExceeded` once `budget_cap_usd` is reached; the run loop catches that and stops cleanly. A fresh `TradingAgentsGraph` is instantiated per `(ticker, decision_date)` so each decision reloads prior-date persisted memories and per-run mutable state (`self.ticker` / `log_states_dict`) stays isolated. `--dry-run` swaps in `StubChatModel` (canned `TradeRecommendation` JSON keyed by prompt keywords) so the harness can be validated against real cached OHLCV in seconds.

### CLI / TUI dispatch (`__main__.py`, `interface/`)

`main()` intercepts `--help` / `-h` / `help` and renders Rich panels via `interface/help.py` (replacing fire's default less-style pager), then hands the rest to `fire.Fire({"cli": run_cli, "tui": run_tui, "reflect": run_reflect, "backtest": run_backtest})`. `interface/display.MessageRenderer` is the Rich callback wired into `TradingAgentsGraph.propagate(..., on_message=renderer)` so streamed LangGraph messages render as Markdown / pretty-JSON panels with truncation. `make_final_decision_panel(recommendation: TradeRecommendation)` is the renderer used by both CLI and TUI for the structured final output (signal / size / target / stop / horizon / confidence / rationale + optional warning banner).

### Output

Per run, `TradingAgentsGraph._log_state` writes to `<config.results_dir>/<TICKER>/`:

- `full_states_log_<TICKER>_<DATE>.json` — final structured state per run date, wrapped as `{"schema_version": 2, "runs": {...}}`; `final_trade_recommendation` (the `TradeRecommendation` dump) is included so reflect / backtest can rebuild it later. `interface/reflect._normalise_state_log_payload` transparently upgrades v1 (un-versioned, flat) logs on read.
- `conversation_log_<TICKER>_<DATE>.txt` — pretty-printed message stream
- `conversation_log_<TICKER>_<DATE>.json` — `messages_to_dict` of the full stream

`results_dir` defaults to `./results`; `data_cache_dir` (15-year OHLCV CSV cache for `stockstats`) is automatically `<results_dir>/data_cache`.

## Code style invariants

These are tightly enforced and reviewers care; full rationale lives in `CONTRIBUTING.md`.

- **Pydantic everywhere** — every config / state / service class subclasses `BaseModel`. Every `Field()` has `default` (or `default_factory`) + `title` + `description`. Mutable defaults always use `default_factory=`. Nested Pydantic models default via `default_factory=NestedModel`, never `default=NestedModel()`. `model_config = ConfigDict(arbitrary_types_allowed=True)` only when the model holds non-Pydantic types (LLM clients, `ToolNode`, etc.). Side effects after construction belong in `@model_validator(mode="after")` returning `"ClassName"` (string forward ref).
- **Cached derived state** — use `@computed_field` stacked directly over `@cached_property` for expensive lazily-built values (LLM instances, compiled graph). See `TradingAgentsGraph` for the canonical pattern.
- **Type hints** — PEP 604 / lowercase generics only. Avoid bare `Any` in `@computed_field` returns. LLM types use the `ChatModel` union from `tradingagents.llm`, not `BaseChatModel`.
- **Paths** — `pathlib.Path` only. Never `os.path.*`, `os.getcwd()`, `os.path.join`. Anchor with `Path(__file__).resolve().parent`. Path defaults go in module-level `_CONSTANT` names, never inlined inside `Field(default=...)`.
- **LangGraph nodes** — signature `(state: AgentState) -> dict[str, Any]`. State updates as typed instances (`InvestDebateState(...)`), not raw dicts. Initial state via `Propagator.create_initial_state()`. Use `HumanMessage(content=...)`, not `("human", ...)` tuples.
- **Pre-commit hooks** — run `make fmt` before committing; do not skip hooks.

## Canonical examples (read these before writing similar code)

| Pattern                   | File                                           | Symbol                        |
| ------------------------- | ---------------------------------------------- | ----------------------------- |
| Pure config model         | `config.py`                                    | `TradingAgentsConfig`         |
| Stateful service class    | `graph/trading_graph.py`                       | `TradingAgentsGraph`          |
| LangGraph state schema    | `agents/utils/agent_states.py`                 | `AgentState`                  |
| Provider-agnostic LLM     | `llm.py`                                       | `build_chat_model`            |
| `@tool`-wrapped function  | `agents/utils/core_stock_tools.py`             | `get_stock_data`              |
| Agent node creator        | `agents/researchers/bull_researcher.py`        | `create_bull_*`               |
| Preprocessor node         | `agents/preprocessors/situation_summariser.py` | `create_situation_summariser` |
| Structured output parser  | `graph/signal_processing.py`                   | `TradeRecommendation`         |
| Conditional routing       | `graph/conditional_logic.py`                   | `ConditionalLogic`            |
| Post-trade reflection     | `graph/reflection.py`                          | `Reflector`                   |
| Backtest driver           | `backtest.py`                                  | `Backtester`                  |
| State-log v1→v2 migration | `interface/reflect.py`                         | `_migrate_state_log_v1_to_v2` |
