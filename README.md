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
```

### Run the CLI

```bash
uv run tradingagents
# or
uv run cli
```

### Run Programmatically

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

## 🧰 Commands Reference

```bash
# Development
make help               # List available make targets
make clean              # Clean caches, artifacts and generated docs
make format             # Run all pre-commit hooks
make test               # Run pytest across the repository
make gen-docs           # Generate docs from src/ and scripts/

# Dependencies (via uv)
make uv-install         # Install uv on your system
uv add <pkg>            # Add production dependency
uv add <pkg> --dev      # Add development dependency
uv sync --group dev     # Install dev-only deps (pre-commit, poe, notebook)
uv sync --group test    # Install test-only deps
uv sync --group docs    # Install docs-only deps
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

## 📚 Documentation

- Live docs are built with MkDocs Material.
- Generate API docs locally and serve:

```bash
uv sync --group docs
make gen-docs
uv run mkdocs serve    # http://localhost:9987
```

## 🐳 Docker and Local Services

`docker-compose.yaml` includes optional services for local development: `redis`, `postgresql`, `mongodb`, `mysql`, and an example `app` service that runs the CLI.

Create a `.env` file to configure ports and credentials (defaults shown):

```bash
REDIS_PORT=6379
POSTGRES_PORT=5432
MONGO_PORT=27017
MYSQL_PORT=3306
```

Run services:

```bash
docker compose up -d redis

# Or run the example app container
docker compose up -d app
```

## 📦 Packaging and Distribution

Build artifacts with uv (wheel and sdist go to `dist/`):

```bash
uv build
```

Publish to PyPI (requires `UV_PUBLISH_TOKEN`):

```bash
UV_PUBLISH_TOKEN=... uv publish
```

## 🧭 Optional Task Runner (Poe the Poet)

Convenience tasks are defined under `[tool.poe.tasks]` in `pyproject.toml`:

```bash
uv run poe docs        # generate + serve docs
uv run poe gen         # generate + deploy docs (gh-deploy)
uv run poe main        # run CLI entry (same as uv run tradingagents)
```

## 🔁 CI/CD Actions Overview

All workflows live in `.github/workflows/`.

- **Tests** (`test.yml`) — Runs pytest on Python 3.11/3.12/3.13/3.14
- **Code Quality** (`code-quality-check.yml`) — Runs ruff and pre-commit hooks
- **Docs Deploy** (`deploy.yml`) — Builds and publishes MkDocs to GitHub Pages
- **Build and Release** (`build_release.yml`) — Builds multi-platform executables and Python packages on tag push
- **Publish Docker Image** (`build_image.yml`) — Builds and pushes Docker image to GHCR
- **Release Drafter** (`release_drafter.yml`) — Maintains draft releases based on Conventional Commits

## 🤝 Contributing

- Open issues/PRs
- Follow the coding style (ruff, type hints)
- Use Conventional Commit messages and descriptive PR titles

## 📄 License

MIT — see `LICENSE`.
