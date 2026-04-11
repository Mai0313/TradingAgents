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

🚀 **TradingAgents** 是一個多 Agent LLM 金融交易框架，利用大型語言模型模擬分析師團隊、研究辯論和投資組合管理決策，以提供股票交易分析。

其他語言: [English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

## ✨ 重點特色

- 基於 **LangGraph** 和 **AG2** (AutoGen) 建構，提供穩健的多 Agent 編排機制
- 多 Agent 架構：分析師團隊 → 研究團隊 → 交易員 → 風險管理 → 投資組合管理
- 支援多種 LLM 供應商：OpenAI、Anthropic、Google Gemini、xAI (Grok)、OpenRouter、Ollama
- 市場數據全由 `yfinance` 提供：OHLCV、基本面、技術指標、新聞與內部人交易
- 基於 Pydantic 的設定系統，提供嚴格型別檢查與驗證
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
```

### 使用方式

```python
from tradingagents.default_config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = TradingAgentsConfig(
    llm_provider="openai",
    deep_think_llm="gpt-5.2",
    quick_think_llm="gpt-5-mini",
    max_debate_rounds=1,
)

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
    ├── dataflows/        # yfinance 數據擷取
    ├── graph/            # LangGraph 交易圖設定
    ├── llm_clients/      # LLM 供應商客戶端（OpenAI、Anthropic、Google、xAI、OpenRouter、Ollama）
    └── default_config.py # 預設設定
```

## 🤖 Agent 工作流程

TradingAgents 透過 LangGraph `StateGraph` 編排 **12 個 LLM agent** 加上 **2 個支援元件**，每次執行會依序跑過 4 個 phase，所有狀態（各類 report、debate transcript、trade decision）都透過一個共用的 Pydantic `AgentState` 在所有節點之間傳遞。

> 完整架構參考文件：[DESIGN.md](DESIGN.md)。

### Phase 1 — 分析師團隊（資料蒐集）

四位 analyst 依序執行。每位 analyst 的 LLM 都會 `bind_tools(...)` 到一組以 `yfinance` 為 backend 的 `@tool` 函式，並與其專屬的 `ToolNode` 配對，持續 loop 直到沒有新的 tool call 為止。每位 analyst 結束之後會經過一個 `Msg Clear` node，它會發出 `RemoveMessage` 並補上一個 `HumanMessage("Continue")` placeholder（這是為了維持 Anthropic 對最後一則訊息必須是 human 的要求）。

| Analyst                  | LLM 綁定的 tools                                                                | 寫入 state            |
| ------------------------ | ------------------------------------------------------------------------------- | --------------------- |
| **Market Analyst**       | `get_stock_data`, `get_indicators`                                              | `market_report`       |
| **Social Media Analyst** | `get_news`                                                                      | `sentiment_report`    |
| **News Analyst**         | `get_news`, `get_global_news`                                                   | `news_report`         |
| **Fundamentals Analyst** | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | `fundamentals_report` |

Market Analyst 可挑選的 technical indicator（一次最多 8 個）：`close_50_sma`、`close_200_sma`、`close_10_ema`、`macd`、`macds`、`macdh`、`rsi`、`boll`、`boll_ub`、`boll_lb`、`atr`、`vwma`。

### Phase 2 — 研究辯論

- **Bull Researcher** 與 **Bear Researcher** 會依照 `max_debate_rounds`（預設為 1，等於雙方各講一輪）互相辯論，依據「上一位發言者是誰」決定下一個輪到誰。每位 researcher 會先用自己的 `FinancialSituationMemory` 做 BM25 retrieval，把 top-k 的過往經驗灌進 prompt 再開講。
- 終止條件：當 `count >= 2 * max_debate_rounds` 時，graph 會 route 到 **Research Manager**（deep-thinking LLM），由它彙整整場辯論、產出 `investment_plan`，並填入 `investment_debate_state.judge_decision`。

### Phase 3 — Trader

**Trader**（quick-thinking LLM）會讀取 `investment_plan` 以及來自 `trader_memory` 的 top-k 歷史經驗，輸出 `trader_investment_plan`。它的輸出必須以 `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**` 結尾。

### Phase 4 — 風險辯論

三位 risk debator 以固定順序輪流發言：**Aggressive → Conservative → Neutral → Aggressive → …**，循環 `max_risk_discuss_rounds` 輪（預設為 1，代表每種立場各發言一次）。終止條件：當 `count >= 3 * max_risk_discuss_rounds` 時，graph route 到 **Risk Judge**（由 `create_risk_manager` 建立的 deep-thinking LLM），由它修正 trader 的計畫並寫入 `final_trade_decision`。最後再由一個輕量的 `SignalProcessor` LLM 把這段自然語言決策抽成單一 token — `BUY` / `SELL` / `HOLD`。

### 支援元件

- **FinancialSituationMemory** — 採 BM25Okapi 做 retrieval，整個流程共有 5 個 instance（bull、bear、trader、invest_judge、risk_manager）。純 lexical 相似度，不需要任何 embedding API。
- **Reflector** — 交易結果出爐之後，呼叫 `TradingAgentsGraph.reflect_and_remember(returns_losses)` 會針對 5 個 memory 各跑一輪 post-trade reflection，把這次的成敗寫回對應的 memory 供之後 retrieval 使用。

### 流程示意

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

每次執行的完整 state 會寫入 `eval_results/<股票代碼>/TradingAgentsStrategy_logs/full_states_log_<日期>.json`。

## 🤝 貢獻

有關開發說明（包含文件、測試和 Docker 服務等），請參閱 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 歡迎 Issue/PR
- 請遵循程式風格（ruff、型別）
- PR 標題遵循 Conventional Commits

## 📄 授權

MIT — 詳見 `LICENSE`。
