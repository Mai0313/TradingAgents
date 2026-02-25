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
- 支援多種 LLM 供應商：OpenAI、Anthropic、Google Gemini
- 多種數據供應商：`yfinance`、Alpha Vantage
- 帶有即時進度顯示的互動式 CLI
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
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
```

### 執行 CLI

```bash
uv run tradingagents
# 或
uv run cli
```

### 作為函式庫使用

您也可以在自己的腳本中以程式化方式使用 `TradingAgents`：

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

## 🧰 指令一覽

```bash
# 開發
make help               # 顯示 Makefile 指令列表
make clean              # 清理快取、產物與產生的文件
make format             # 執行所有 pre-commit hooks
make test               # 執行 pytest
make gen-docs           # 從 src/ 與 scripts/ 生成文件

# 依賴管理（uv）
make uv-install         # 安裝 uv
uv add <pkg>            # 加入正式依賴
uv add <pkg> --dev      # 加入開發依賴
uv sync --group dev     # 安裝開發用依賴（pre-commit、poe、notebook）
uv sync --group test    # 安裝測試用依賴
uv sync --group docs    # 安裝文件用依賴
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
    │   └── static/       # 靜態資源（歡迎畫面）
    ├── dataflows/        # 數據擷取與供應商路由
    ├── graph/            # LangGraph 交易圖設定
    ├── llm_clients/      # LLM 供應商客戶端
    └── default_config.py # 預設設定
```

## 🤖 Agent 工作流程

1. **分析師團隊** — 每位選定的分析師獨立研究市場數據、新聞、情緒和基本面
2. **研究團隊** — 多頭和空頭研究員辯論；研究經理做出最終投資決策
3. **交易員** — 根據研究制定交易計劃
4. **風險管理** — 三位風險分析師（激進、中性、保守）辯論風險
5. **投資組合管理者** — 根據所有輸入做出最終交易決策

## 📚 文件系統

使用 MkDocs Material，生成與預覽：

```bash
uv sync --group docs
make gen-docs
uv run mkdocs serve    # http://localhost:9987
```

## 🐳 Docker 與本機服務

`docker-compose.yaml` 內提供本機開發常見服務：`redis`、`postgresql`、`mongodb`、`mysql`。

```bash
docker compose up -d redis

# 或啟動示範 app
docker compose up -d app
```

## 📦 打包與發佈

以 uv 產出套件（wheel/sdist 會放在 `dist/`）：

```bash
uv build
```

發佈到 PyPI（需設定 `UV_PUBLISH_TOKEN`）：

```bash
UV_PUBLISH_TOKEN=... uv publish
```

## 🧭 選用任務管理（Poe the Poet）

```bash
uv run poe docs        # 生成 + 啟動文件預覽
uv run poe gen         # 生成 + 發佈文件（gh-deploy）
uv run poe main        # 執行 CLI（等同 uv run tradingagents）
```

## 🔁 CI/CD 工作流程總覽

所有流程位於 `.github/workflows/`：

- **Tests**（`test.yml`）— 執行 pytest（3.11/3.12/3.13/3.14）
- **Code Quality**（`code-quality-check.yml`）— 執行 ruff 與 pre-commit hooks
- **Docs Deploy**（`deploy.yml`）— 建置並發布 MkDocs 網站到 GitHub Pages
- **Build and Release**（`build_release.yml`）— 建置多平台可執行檔與 Python 套件
- **Publish Docker Image**（`build_image.yml`）— 發佈至 GHCR
- **Release Drafter**（`release_drafter.yml`）— 基於 Conventional Commits 維護草稿發佈

## 🤝 貢獻

- 歡迎 Issue/PR
- 請遵循程式風格（ruff、型別）
- PR 標題遵循 Conventional Commits

## 📄 授權

MIT — 詳見 `LICENSE`。
