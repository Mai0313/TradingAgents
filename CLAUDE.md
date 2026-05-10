# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependency / environment (managed by `uv`, not pip):

```bash
make uv-install           # install uv itself (one-time)
uv sync                   # install runtime deps
uv sync --group dev       # add pre-commit / poethepoet / notebook
uv sync --group docs      # add MkDocs deps
uv add <pkg>              # add runtime dep
uv add <pkg> --dev        # add dev dep
```

Running the pipeline (the project ships a `tradingagents` console script registered in `[project.scripts]`):

```bash
uv run tradingagents tui                              # interactive questionary prompts
uv run tradingagents cli                              # all defaults (GOOG, today, gemini-3.1-pro-preview)
uv run tradingagents cli --ticker AAPL --date 2024-05-10
uv run tradingagents cli --llm_provider openai --deep_think_llm gpt-5 --quick_think_llm gpt-5-mini
uv run tradingagents reflect --ticker AAPL --date 2024-05-10 --returns 0.032   # apply post-trade reflection (see Memory section)
uv run tradingagents --help                           # rich-rendered top-level help
uv run tradingagents cli --help                       # rich-rendered per-command flags
python -m tradingagents cli ...                       # equivalent
uv run python main.py                                 # legacy script-style entrypoint at repo root
uv run poe cli / uv run poe tui                       # poethepoet aliases
```

Quality gates:

```bash
make format               # uv run pre-commit run -a (ruff, mypy, codespell, mdformat, gitleaks, uv-sync, ...)
make clean                # nuke caches, dist, docs, .github/reports
make gen-docs             # build MkDocs Material site (writes to docs/, then `uv run mkdocs serve` on :9987)
```

Tests: a small **mock-based** pytest suite lives under `tests/` (added in #35). It exercises pure helpers and graph wiring via `monkeypatch` only — **no live LLM or yfinance network calls**, so it is safe and free to run via `make test` / `uv run pytest`. Update the existing tests when changing the contracts they pin (e.g. error-message format, public function names, no-data sentinels), and feel free to add similarly mock-based tests when you change shared invariants. Do **not** propose tests that require real LLM API or yfinance traffic — each live LangGraph run hits paid LLM APIs and costs real money. Coverage gate (`--cov-fail-under=80`) is currently aspirational; the suite covers a fraction of the codebase.

API keys (one of these is required, picked by `llm_provider`): `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`. See `.env.example`.

## Architecture

### One-line summary

A LangGraph `StateGraph` orchestrates 12 LLM agent nodes plus per-agent BM25 memories through 4 sequential phases (Analysts → Research debate → Trader → Risk debate), driven by a single `TradingAgentsConfig` and exposing both a programmatic API (`TradingAgentsGraph.propagate(ticker, date)`) and a fire-driven CLI/TUI.

### Big picture flow (`src/tradingagents/graph/setup.py`)

```
START
 → [Market Analyst ⇄ tools_market]   → Msg Clear
 → [Social Analyst ⇄ tools_social]   → Msg Clear
 → [News Analyst ⇄ tools_news]       → Msg Clear
 → [Fundamentals Analyst ⇄ tools_fundamentals] → Msg Clear
 → [Bull Researcher ⇄ Bear Researcher] × max_debate_rounds
 → Research Manager → Trader
 → [Aggressive → Conservative → Neutral] × max_risk_discuss_rounds
 → Risk Judge → END
```

Each analyst phase is an LLM-with-tools loop terminated by `should_continue_<analyst>` in `graph/conditional_logic.py`. Between analysts a `Msg Clear` node emits `RemoveMessage` for every prior message plus a placeholder `HumanMessage("Continue")` so Anthropic's strict alternating-role validation does not blow up. **Don't remove that placeholder** — it's load-bearing for Anthropic.

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

`TradingAgentsConfig` is a Pydantic model with no defaults for `llm_provider` / `deep_think_llm` / `quick_think_llm` / `max_debate_rounds` / `max_risk_discuss_rounds` / `max_recur_limit` (caller must supply). `data_cache_dir` is a `@computed_field` under `results_dir`. A module-level `_config_container` and `set_config()` / `get_config()` form a process-global singleton; `TradingAgentsGraph._setup` (a `model_validator(mode="after")`) registers the active config so deeply-nested code (e.g. `dataflows/yfinance._get_stock_stats_bulk`, `agents/prompts.__init__._language_instruction`) can read it without prop-drilling. **Always construct a config and pass it to `TradingAgentsGraph` first**, otherwise tools / prompts that call `get_config()` raise `RuntimeError`.

### Tools and dataflows

Agent tools (`agents/utils/{core_stock,fundamental_data,news_data,technical_indicators}_tools.py`) are thin `@tool`-decorated wrappers over plain functions in `dataflows/yfinance.py` and `dataflows/news.py`. The Market Analyst gets `get_stock_data` + `get_indicators`; Social gets `get_news`; News gets `get_news` + `get_global_news` + `get_insider_transactions`; Fundamentals gets `get_fundamentals` + `get_balance_sheet` + `get_cashflow` + `get_income_statement`. Tool-to-analyst wiring lives in `TradingAgentsGraph.tool_nodes`.

Supported technical indicators (Market Analyst can pick up to 8 per run): `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`, `mfi` — defined in `_get_stock_stats_bulk`'s `best_ind_params` dict.

Ticker resolution (`dataflows/tickers.py`): bare symbols are resolved via `yf.Search`; pure-digit symbols also try `<DIGITS>.TW` and `<DIGITS>.TWO` (Taiwan stocks like `2330`, `8069`); explicit suffixed symbols (`AAPL`, `2330.TW`) bypass search.

### Memory (`agents/utils/memory.py`)

`FinancialSituationMemory` is a Pydantic `BaseModel` using **BM25Okapi** (lexical, no embeddings API). `TradingAgentsGraph` constructs five instances: `bull_memory`, `bear_memory`, `trader_memory`, `invest_judge_memory`, `risk_manager_memory`. Each is wired to `<config.data_cache_dir>/memories/<name>.jsonl`; the file is auto-loaded on construction and atomically rewritten on every `add_situations(...)` call so reflections persist across processes. Each researcher / judge calls `get_memories(state.combined_reports, n_matches=k)` before reasoning.

After the trade outcome is known, run `tradingagents reflect --ticker X --date Y --returns Z` (or call `TradingAgentsGraph.reflect_and_remember(returns, state=...)` programmatically). The CLI subcommand reads `<results_dir>/<TICKER>/full_states_log_<TICKER>_<DATE>.json`, reconstructs the `AgentState`, runs `Reflector` over each component, and appends the lessons to the JSONL files. The reflector grades reasoning quality (decision-process correctness), not just realised P/L — see `prompts/reflector.md`.

### Prompts (`agents/prompts/`)

Every agent's system / user prompt is a separate `.md` file (e.g. `bull_researcher.md`, `risk_manager.md`, `trader_system.md`, `trader_user.md`). Load via `load_prompt(name)` and call `.format(**kwargs)` on the result. **Never inline prompts as Python string literals.** `load_prompt` automatically appends a "Please respond in <BCP47>." line read from the active `TradingAgentsConfig.response_language`, so prompts must use `{{` and `}}` to escape literal braces.

### CLI / TUI dispatch (`__main__.py`, `interface/`)

`pyproject.toml` registers `tradingagents = "tradingagents.__main__:main"`. `main()` intercepts `--help` / `-h` / the literal `help` token and renders Rich panels via `interface/help.py` (replacing fire's default less-style pager), then hands the rest to `fire.Fire({"cli": run_cli, "tui": run_tui})`. `python -m tradingagents` resolves to the same function — there's only one routing surface. `interface/display.MessageRenderer` is the Rich-based callback wired into `TradingAgentsGraph.propagate(..., on_message=renderer)` so streamed LangGraph messages render as Markdown / pretty-JSON panels with truncation.

### Output

Per run, `TradingAgentsGraph._log_state` writes to `<config.results_dir>/<TICKER>/`:

- `full_states_log_<TICKER>_<DATE>.json` — final structured state per run date
- `conversation_log_<TICKER>_<DATE>.txt` — pretty-printed message stream
- `conversation_log_<TICKER>_<DATE>.json` — `messages_to_dict` of the full stream

`results_dir` defaults to `./results`; `data_cache_dir` (15-year OHLCV CSV cache for `stockstats`) is automatically `<results_dir>/data_cache`.

## Code style invariants

These are tightly enforced and reviewers care; full rationale lives in `CONTRIBUTING.md`.

- **Pydantic everywhere** — every config / state / service class subclasses `BaseModel`. Every `Field()` has `default` (or `default_factory`) + `title` + `description`. Mutable defaults always use `default_factory=`. Nested Pydantic models default via `default_factory=NestedModel`, never `default=NestedModel()`. `model_config = ConfigDict(arbitrary_types_allowed=True)` only when the model holds non-Pydantic types (LLM clients, `ToolNode`, etc.). Side effects after construction belong in `@model_validator(mode="after")` returning `"ClassName"` (string forward ref).
- **Cached derived state** — use `@computed_field` stacked directly over `@cached_property` for expensive lazily-built values (LLM instances, compiled graph). See `TradingAgentsGraph` for the canonical pattern.
- **Type hints** — PEP 604 / lowercase generics only: `X | None`, `list[X]`, `dict[str, X]`. Never `Optional[X]` / `List[X]` / `Dict[...]`. Avoid bare `Any` in `@computed_field` returns. LLM types use the `ChatModel` union from `tradingagents.llm`, not `BaseChatModel`.
- **Paths** — `pathlib.Path` only. Never `os.path.*`, `os.getcwd()`, `os.path.join`. Anchor with `Path(__file__).resolve().parent`. Path defaults go in module-level `_CONSTANT` names, never inlined inside `Field(default=...)`.
- **LangGraph nodes** — signature `(state: AgentState) -> dict[str, Any]`. State updates as typed instances (`InvestDebateState(...)`), not raw dicts. Initial state via `Propagator.create_initial_state()`. Use `HumanMessage(content=...)`, not `("human", ...)` tuples.
- **Prompts** — `.md` files under `agents/prompts/<snake_case>.md`, loaded with `load_prompt(name)`. Escape literal braces as `{{` / `}}`.
- **Commits** — Conventional Commits, English only. CI must pass; pre-commit hooks (ruff, mdformat, codespell, mypy, gitleaks, uv-sync, uv-lock) should not be skipped.

## Canonical examples (read these before writing similar code)

| Pattern                  | File                                    | Symbol                |
| ------------------------ | --------------------------------------- | --------------------- |
| Pure config model        | `config.py`                             | `TradingAgentsConfig` |
| Stateful service class   | `graph/trading_graph.py`                | `TradingAgentsGraph`  |
| LangGraph state schema   | `agents/utils/agent_states.py`          | `AgentState`          |
| Provider-agnostic LLM    | `llm.py`                                | `build_chat_model`    |
| `@tool`-wrapped function | `agents/utils/core_stock_tools.py`      | `get_stock_data`      |
| Agent node creator       | `agents/researchers/bull_researcher.py` | `create_bull_*`       |
| Conditional routing      | `graph/conditional_logic.py`            | `ConditionalLogic`    |
| Post-trade reflection    | `graph/reflection.py`                   | `Reflector`           |
