# TradingAgents — Copilot Instructions

## Project Overview

**TradingAgents** is a multi-agent LLM financial trading framework built on **LangGraph** (orchestration) and **AG2/AutoGen** (agent communication). It simulates analyst teams, research debates, and portfolio management decisions for stock trading analysis.

## Architecture

```
src/tradingagents/
├── agents/           # All agent implementations
│   ├── analysts/     # market, news, social, fundamentals — each returns a state-dict node function
│   ├── managers/     # research_manager, risk_manager
│   ├── researchers/  # bull_researcher, bear_researcher
│   ├── risk_mgmt/    # aggressive, neutral, conservative debators
│   ├── trader/       # trader agent
│   └── utils/        # agent_states.py (TypedDict state), agent_utils.py (abstract tool wrappers), memory.py
├── cli/              # Typer-based interactive CLI (entrypoint: cli.main:app)
├── dataflows/        # Data vendors (yfinance, Alpha Vantage) + routing interface
├── graph/            # LangGraph graph definition, propagation, reflection, signal_processing
├── llm_clients/      # Provider-abstracted LLM clients (OpenAI, Anthropic, Google, xAI, Ollama, OpenRouter)
└── default_config.py # Single source of truth for all runtime config keys
```

**Data flow:** `TradingAgentsGraph.propagate(ticker, date)` → LangGraph runs analyst nodes in parallel → Bull/Bear debate → Trader → Risk debate → Portfolio Manager → `(state, final_decision)`.

## Build & Run Commands

```bash
# Setup
make uv-install          # Install uv (once)
uv sync                  # Install all deps
cp .env.example .env     # Add API keys

# Run CLI
uv run tradingagents

# Use as library
from tradingagents.graph.trading_graph import TradingAgentsGraph
ta = TradingAgentsGraph(debug=True, config={...})
_, decision = ta.propagate("NVDA", "2024-05-10")

# Development
uv run pre-commit run -a  # ruff + pre-commit (always run before committing)
make test                # pytest with coverage (must stay ≥ 80%)
make gen-docs            # regenerate MkDocs API reference

# Docs
uv sync --group docs
uv run mkdocs serve      # http://localhost:9987
```

## Key Conventions

### Python Style

- **Python ≥ 3.11**; use `X | Y` union syntax, `list[str]` built-in generics (not `List`, `Optional`)
- **Line length:** 99 characters (ruff enforced)
- **Type annotations required** on all public functions and methods (`ANN` rules enabled)
- **Ruff** is the linter/formatter; `unsafe-fixes = true`
- **All formatting issues must be fixed via `uv run pre-commit run -a`** — never manually reformat code or run `ruff` directly
- **Docstrings** follow Google style (`D` rules enabled)
- **Import order:** isort managed by ruff; `src/` and `tests/` are the import roots

### Agent Pattern

Each agent is a **factory function** `create_<name>(llm) -> Callable[[state_dict], state_dict]`:

```python
def create_market_analyst(llm: BaseChatModel) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def market_analyst_node(state: dict[str, Any]) -> dict[str, Any]: ...

    return market_analyst_node
```

Agents never import from sibling agents; shared utilities live in `agents/utils/`.

### Tool / Data Vendor Pattern

- Abstract tool wrappers live in `agents/utils/agent_utils.py` (e.g., `get_stock_data`, `get_news`)
- Routing by vendor is handled in `dataflows/interface.py` based on `config["data_vendors"]`
- Default vendors: `yfinance` for all categories; `alpha_vantage` available as alternative
- Never call vendor APIs directly from agent files — always go through the abstract wrapper

### Configuration

- All config keys are defined in `default_config.py` — add new keys there first
- Pass config as a dict to `TradingAgentsGraph(config=...)` or via CLI (which builds the dict)
- `dataflows.config.set_config(config)` must be called before running the graph (done automatically in `TradingAgentsGraph.__init__`)

### LLM Clients

- Use `create_llm_client(provider, model, base_url=None, **kwargs)` from `llm_clients/factory.py`
- `provider` values: `"openai"`, `"anthropic"`, `"google"`, `"xai"`, `"ollama"`, `"openrouter"`
- `xai` and `ollama` both reuse `OpenAIClient` with a custom `base_url`
- All clients extend `BaseLLMClient` — implement `bind_tools()` and `invoke()` when adding a provider

### Results

Analysis output is written to `results/<TICKER>/<DATE>/` with per-agent markdown reports and a `complete_report.md`.

## Testing

- Test files in `tests/` following `test_*.py` naming
- Run with `pytest` (or `make test`); parallel execution via `pytest-xdist` (`-n=auto`)
- Coverage threshold: **80%** (`--cov-fail-under=80`)
- Async tests: `asyncio_mode = "auto"` — use `async def test_*` freely
- Mark slow tests with `@pytest.mark.slow`; CI-only skips with `@pytest.mark.skip_when_ci`

## Dependency Management

- Use **uv** exclusively — never `pip install` directly
- Add production deps: `uv add <pkg>`
- Add dev/test deps: `uv add <pkg> --dev` or `uv add <pkg> --group test`
- Dependency groups: `dev`, `test`, `docs`

## Commit & PR Guidelines

- Follow **Conventional Commits** (`feat:`, `fix:`, `docs:`, `refactor:`, etc.)
- Run `uv run pre-commit run -a` and `make test` locally before pushing
- PRs require passing CI: tests (Python 3.11–3.14) + code-quality checks

## Common Pitfalls

- **Do not** import from `tradingagents.dataflows.*` directly in agent files; use `agent_utils.py` wrappers
- **Do not** use `Optional[X]` or `List[X]` — use `X | None` and `list[X]`
- The `data_cache_dir` points inside the package (`src/.../dataflows/data_cache/`) — cached CSVs live there
- `TRADINGAGENTS_RESULTS_DIR` env var overrides the default `./results` output path
- Pre-commit hooks include `codespell` — watch for typos in string literals and comments
