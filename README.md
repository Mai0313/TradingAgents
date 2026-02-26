<div align="center" markdown="1">

# TradingAgents

[![PyPI version](https://img.shields.io/pypi/v/tradingagents.svg)](https://pypi.org/project/tradingagents/)
[![python](https://img.shields.io/badge/-Python_%7C_3.11%7C_3.12%7C_3.13%7C_3.14-blue?logo=python&logoColor=white)](https://www.python.org/downloads/source/)
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

- Multi-agent architecture: Analyst Team → Research Team → Trader → Risk Management → Portfolio Management
- Support for multiple LLM providers: OpenAI, Anthropic, Google Gemini
- Multiple data vendors: `yfinance`, Alpha Vantage
- Interactive CLI with real-time progress display
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
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
ALPHA_VANTAGE_API_KEY=... # Optional
```

### Run the CLI

```bash
uv run tradingagents
# or
uv run cli
```

### Use as a Library

You can also use `TradingAgents` programmatically in your own scripts:

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-4o"
config["quick_think_llm"] = "gpt-4o-mini"
config["max_debate_rounds"] = 1
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
}

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
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
    ├── cli/              # Interactive CLI application
    │   ├── main.py       # CLI entrypoint (Typer app)
    │   ├── utils.py      # CLI helper functions
    │   └── static/       # Static assets (welcome screen)
    ├── dataflows/        # Data ingestion & vendor routing
    ├── graph/            # LangGraph trading graph setup
    ├── llm_clients/      # LLM provider clients
    └── default_config.py # Default configuration
```

## 🤖 Agent Workflow

1. **Analyst Team** — Each selected analyst independently researches market data, news, sentiment, and fundamentals
2. **Research Team** — Bull and Bear researchers debate; Research Manager makes a final investment decision
3. **Trader** — Formulates a trade plan based on research
4. **Risk Management** — Three risk analysts (aggressive, neutral, conservative) debate risk
5. **Portfolio Manager** — Makes the final trade decision based on all inputs

## 🤝 Contributing

For development instructions including documentation, testing, and Docker services, please see [CONTRIBUTING.md](CONTRIBUTING.md).

- Open issues/PRs
- Follow the coding style (ruff, type hints)
- Use Conventional Commit messages and descriptive PR titles

## 📄 License

MIT — see `LICENSE`.
