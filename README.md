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
- Multi-agent architecture: Analyst Team → Research Team → Trader → Risk Management → Portfolio Management
- Powered by `langchain.chat_models.init_chat_model`; supports any provider keyed via an explicit `llm_provider` field plus a model name (OpenAI, Anthropic, Google Gemini, xAI (Grok), OpenRouter, Ollama, HuggingFace, LiteLLM)
- Unified `reasoning_effort` knob (`low / medium / high / xhigh / max`) mapped per provider to native parameters (Anthropic `effort`, OpenAI `reasoning_effort`, Google `thinking_level`)
- Market data powered by `yfinance` for OHLCV, fundamentals, technical indicators, news, and insider transactions
- Pydantic-based configuration with strict typing and validation
- Analysis results automatically saved to `results/` with organized subfolders
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
    response_language="en",
)

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

`llm_provider` is one of the `langchain.chat_models.init_chat_model` registry keys (`openai`, `anthropic`, `google_genai`, `xai`, `openrouter`, `ollama`, `huggingface`, `litellm`); `deep_think_llm` / `quick_think_llm` take the model name as accepted by that provider (`gpt-5`, `claude-sonnet-4-6`, `gemini-3-pro-preview`, `grok-4`, ...).

Set `response_language` to control the language requested in all agent prompts. Tickers without exchange suffixes are resolved automatically with Yahoo Finance Search. For Taiwan stocks, pass the numeric stock code directly, such as `2330`, `2408`, or `8069`; explicit Yahoo Finance symbols such as `2330.TW`, `8069.TWO`, `AAPL`, and `TSM` are also supported.

```python
config = TradingAgentsConfig(
    llm_provider="openai",
    deep_think_llm="gpt-5",
    quick_think_llm="gpt-5-mini",
    max_debate_rounds=1,
    max_risk_discuss_rounds=1,
    max_recur_limit=100,
    response_language="Traditional Chinese",
)

ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("2330", "2024-05-10")
```

## 📁 Project Structure

```
src/
└── tradingagents/
    ├── agents/           # Agent implementations
    │   ├── analysts/     # Market, News, Social, Fundamentals analysts
    │   ├── managers/     # Research & Portfolio managers
    │   ├── researchers/  # Bull & Bear researchers
    │   ├── risk_mgmt/    # Risk management agents
    │   ├── trader/       # Trader agent
    │   └── utils/        # Shared agent utilities
    ├── dataflows/        # Data ingestion via yfinance
    ├── graph/            # LangGraph trading graph setup
    ├── llm.py            # Chat model construction (init_chat_model wrapper + reasoning_effort mapping)
    ├── config.py         # TradingAgentsConfig schema + global singleton
    └── cli.py            # Entry point
```

## 🤖 Agent Workflow

TradingAgents orchestrates **12 LLM agents** plus **2 supporting components** through a LangGraph `StateGraph`. Every run goes through 4 sequential phases, and the state (reports, debate transcripts, trade decisions) is persisted through a Pydantic `AgentState` shared across all nodes.

### Phase 1 — Analyst Team (Data Collection)

Four analysts run in sequence. Each analyst has its LLM bound to a specific set of `yfinance`-backed `@tool` functions, and loops with its own `ToolNode` until no more tool calls are emitted. Between analysts a `Msg Clear` node resets the conversation history (emitting `RemoveMessage` + a `HumanMessage("Continue")` placeholder for Anthropic compatibility).

| Analyst                  | LLM-bound tools                                                                 | Writes to state       |
| ------------------------ | ------------------------------------------------------------------------------- | --------------------- |
| **Market Analyst**       | `get_stock_data`, `get_indicators`                                              | `market_report`       |
| **Social Media Analyst** | `get_news`                                                                      | `sentiment_report`    |
| **News Analyst**         | `get_news`, `get_global_news`                                                   | `news_report`         |
| **Fundamentals Analyst** | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | `fundamentals_report` |

Supported technical indicators (selected by the Market Analyst, up to 8 per run): `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`.

### Phase 2 — Research Debate

- **Bull Researcher** and **Bear Researcher** debate for `max_debate_rounds` rounds (default: 1 round each), taking turns based on who spoke last. Each researcher retrieves top-k BM25 matches from its own `FinancialSituationMemory` before arguing.
- Termination: `count >= 2 * max_debate_rounds` routes the graph to **Research Manager** (deep-thinking LLM), which evaluates the full debate, produces the `investment_plan`, and populates `investment_debate_state.judge_decision`.

### Phase 3 — Trader

**Trader** (quick-thinking LLM) consumes `investment_plan` plus the top-k `trader_memory` matches and produces `trader_investment_plan`. Its output must end with `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`.

### Phase 4 — Risk Control Debate

Three debators rotate in a fixed order — **Aggressive → Conservative → Neutral → Aggressive → …** — for `max_risk_discuss_rounds` rounds (default: 1 round per stance). Termination: `count >= 3 * max_risk_discuss_rounds` routes to the **Risk Judge** (deep-thinking LLM via `create_risk_manager`), which revises the trader's plan and writes the `final_trade_decision`. A lightweight `SignalProcessor` LLM then extracts the canonical `BUY` / `SELL` / `HOLD` token from that natural-language decision.

### Supporting components

- **FinancialSituationMemory** — BM25Okapi-backed per-agent memory (5 instances: bull, bear, trader, invest_judge, risk_manager). Purely lexical, no external embeddings API required.
- **Reflector** — After the trade outcome is known, `TradingAgentsGraph.reflect_and_remember(returns_losses)` runs post-trade reflection against each of the 5 memories so future runs can learn from past decisions.

### Flow Diagram

```
START
  │
  ▼
[Market Analyst ⇄ tools_market] → Msg Clear
  │
  ▼
[Social Analyst ⇄ tools_social] → Msg Clear
  │
  ▼
[News Analyst ⇄ tools_news] → Msg Clear
  │
  ▼
[Fundamentals Analyst ⇄ tools_fundamentals] → Msg Clear
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
Risk Judge  →  SignalProcessor  →  END
```

Per-run logs are written to `results/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<DATE>.json` (the path resolves from `TradingAgentsConfig.results_dir`, which defaults to `./results`).

## 🤝 Contributing

For development instructions including documentation, testing, and Docker services, please see [CONTRIBUTING.md](CONTRIBUTING.md).

- Open issues/PRs
- Follow the coding style (ruff, type hints)
- Use Conventional Commit messages and descriptive PR titles

## 📄 License

MIT — see `LICENSE`.
