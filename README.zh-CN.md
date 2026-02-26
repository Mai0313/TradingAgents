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

🚀 **TradingAgents** 是一个多 Agent LLM 金融交易框架，利用大型语言模型模拟分析师团队、研究辩论和投资组合管理决策，以提供股票交易分析。

其他语言: [English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

## ✨ 重点特色

- 多 Agent 架构：分析师团队 → 研究团队 → 交易员 → 风险管理 → 投资组合管理
- 支持多种 LLM 供应商：OpenAI、Anthropic、Google Gemini
- 多种数据供应商：`yfinance`、Alpha Vantage
- 带有实时进度显示的交互式 CLI
- 现代 `src/` 布局，完整类型注解
- 通过 `uv` 进行快速依赖管理
- Pre-commit 包链：ruff、mdformat、codespell、mypy、uv hooks
- Pytest + coverage、MkDocs Material 文档系统

## 🚀 快速开始

```bash
git clone https://github.com/Mai0313/TradingAgents.git
cd TradingAgents
make uv-install               # 安装 uv（仅需一次）
uv sync                       # 安装依赖
cp .env.example .env          # 配置 API 密钥
```

### 配置 API 密钥

编辑 `.env` 并设置您的 LLM 供应商密钥：

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
ALPHA_VANTAGE_API_KEY=... # Optional
```

### 运行 CLI

```bash
uv run tradingagents
# 或
uv run cli
```

### 作为库使用

您也可以在自己的脚本中以程序化方式使用 `TradingAgents`：

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

## 📁 项目结构

```
src/
└── tradingagents/
    ├── agents/           # Agent 实现
    │   ├── analysts/     # 市场、新闻、社交、基本面分析师
    │   ├── managers/     # 研究 & 投资组合管理者
    │   ├── researchers/  # 多头 & 空头研究员
    │   ├── risk_mgmt/    # 风险管理 Agents
    │   ├── trader/       # 交易员 Agent
    │   └── utils/        # 共用 Agent 工具
    ├── cli/              # 交互式 CLI 应用程序
    │   ├── main.py       # CLI 入口（Typer app）
    │   ├── utils.py      # CLI 辅助函数
    │   └── static/       # 静态资源（欢迎画面）
    ├── dataflows/        # 数据采集与供应商路由
    ├── graph/            # LangGraph 交易图配置
    ├── llm_clients/      # LLM 供应商客户端
    └── default_config.py # 默认配置
```

## 🤖 Agent 工作流程

1. **分析师团队** — 每位选定的分析师独立研究市场数据、新闻、情绪和基本面
2. **研究团队** — 多头和空头研究员辩论；研究经理做出最终投资决策
3. **交易员** — 根据研究制定交易计划
4. **风险管理** — 三位风险分析师（激进、中性、保守）辩论风险
5. **投资组合管理者** — 根据所有输入做出最终交易决策

## 🤝 贡献

有关开发说明（包含文档、测试和 Docker 服务等），请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 欢迎 Issue/PR
- 请遵循代码风格（ruff、类型）
- PR 标题遵循 Conventional Commits

## 📄 授权

MIT — 详见 `LICENSE`。
