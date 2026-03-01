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

🚀 **TradingAgents** 是一個多 Agent LLM 金融交易框架，利用大型語言模型模擬分析師團隊、研究辯論和投資組合管理決策，以提供股票交易分析。

其他語言: [English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

## ✨ 重點特色

- 多 Agent 架構：分析師團隊 → 研究團隊 → 交易員 → 風險管理 → 投資組合管理
- 支援多種 LLM 供應商：OpenAI、Anthropic、Google Gemini、xAI (Grok)、OpenRouter、Ollama
- 多種數據供應商：`yfinance`、Alpha Vantage
- 帶有即時進度顯示及逐步設定流程的互動式 CLI
- 分析結果自動儲存至 `results/` 目錄並依團隊分資料夾
- 現代 `src/` 佈局，完整型別註解
- 透過 `uv` 進行快速依賴管理
- Pre-commit 套件鏈：ruff、mdformat、codespell、mypy、uv hooks
- Pytest + coverage、MkDocs Material 文件系統

## 🚀 快速開始

```bash
git clone https://github.com/Mai0313/TradingAgents.git
cd TradingAgents
make uv-install               # 安裝 uv（僅需一次）
uv sync                       # 安裝依賴
cp .env.example .env          # 設定 API 金鑰
```

### 設定 API 金鑰

編輯 `.env` 並設定您的 LLM 供應商金鑰：

```bash
# LLM 供應商（設定您使用的那一個）
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
XAI_API_KEY=...
OPENROUTER_API_KEY=...

# 可選數據供應商
ALPHA_VANTAGE_API_KEY=...
```

### 執行 CLI

```bash
uv run tradingagents
# 或
uv run cli
```

CLI 將引導您完成以下步驟：

1. **股票代碼** — 輸入要分析的股票代碼（例如 `NVDA`）
2. **分析日期** — 輸入日期，格式為 `YYYY-MM-DD`
3. **分析師團隊** — 選擇一個或多個分析師（市場、社群、新聞、基本面）
4. **研究深度** — 選擇淺層 / 中等 / 深度辯論輪次
5. **LLM 供應商** — 選擇 OpenAI、Google、Anthropic、xAI、OpenRouter 或 Ollama
6. **思考 Agent** — 選擇快速思考與深度思考 LLM 模型
7. **供應商設定** — 設定推理努力程度（OpenAI）或思考模式（Google Gemini）

### 作為函式庫使用

您也可以在自己的腳本中以程式化方式使用 `TradingAgents`：

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["deep_think_llm"] = "gpt-5.2"
config["quick_think_llm"] = "gpt-5-mini"
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

## 📁 專案結構

```
src/
└── tradingagents/
    ├── agents/           # Agent 實作
    │   ├── analysts/     # 市場、新聞、社群、基本面分析師
    │   ├── managers/     # 研究 & 投資組合管理者
    │   ├── researchers/  # 多頭 & 空頭研究員
    │   ├── risk_mgmt/    # 風險管理 Agents
    │   ├── trader/       # 交易員 Agent
    │   └── utils/        # 共用 Agent 工具
    ├── cli/              # 互動式 CLI 應用程式
    │   ├── main.py       # CLI 入口（Typer app）
    │   ├── utils.py      # CLI 輔助函數
    │   ├── announcements.py  # 啟動公告
    │   ├── stats_handler.py  # LLM/工具呼叫統計
    │   └── static/       # 靜態資源（歡迎畫面）
    ├── dataflows/        # 數據擷取與供應商路由
    ├── graph/            # LangGraph 交易圖設定
    ├── llm_clients/      # LLM 供應商客戶端（OpenAI、Anthropic、Google、xAI、OpenRouter、Ollama）
    └── default_config.py # 預設設定
```

## 🤖 Agent 工作流程

1. **分析師團隊** — 每位選定的分析師獨立研究市場數據、新聞、情緒和基本面
2. **研究團隊** — 多頭和空頭研究員辯論；研究經理做出最終投資決策
3. **交易員** — 根據研究制定交易計劃
4. **風險管理** — 三位風險分析師（激進、中性、保守）辯論風險
5. **投資組合管理者** — 根據所有輸入做出最終交易決策

分析結果儲存至 `results/<股票代碼>/<日期>/`，各團隊報告分資料夾，並產生合併報告 `complete_report.md`。

## 🤝 貢獻

有關開發說明（包含文件、測試和 Docker 服務等），請參閱 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 歡迎 Issue/PR
- 請遵循程式風格（ruff、型別）
- PR 標題遵循 Conventional Commits

## 📄 授權

MIT — 詳見 `LICENSE`。
