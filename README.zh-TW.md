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

- 基於 **LangGraph** 建構，提供穩健的多 Agent 編排機制
- 多 Agent 架構：分析師團隊 → 研究團隊 → 交易員 → 風險管理 → 投資組合管理
- 透過 `langchain.chat_models.init_chat_model` 建構 LLM，使用獨立的 `llm_provider` 欄位加上 model name 指定模型,支援 OpenAI、Anthropic、Google Gemini、xAI (Grok)、OpenRouter、Ollama、HuggingFace、LiteLLM
- 統一的 `reasoning_effort` 旋鈕（`low / medium / high / xhigh / max`）會 map 到各 provider 的 native 參數（Anthropic `effort`、OpenAI `reasoning_effort`、Google `thinking_level`）
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

#### Command line / 互動模式

套件提供 `tradingagents` console script，內含兩個 subcommand：

```bash
uv run tradingagents tui                     # 互動式 questionary 流程
uv run tradingagents cli                     # 全部使用預設值執行
uv run tradingagents cli --ticker AAPL \
    --deep_think_llm gpt-5 \
    --quick_think_llm gpt-5-mini             # 透過 flag 覆寫
uv run tradingagents --help                  # rich 渲染的 top-level help
uv run tradingagents cli --help              # rich 渲染的 per-command flag 列表
```

`tradingagents tui` 會用一連串 questionary prompt 帶你走完所有參數（ticker、日期、provider、models、辯論輪數、analyst 選擇等）；`tradingagents cli` 是同一條流程，但完全用 command-line flag 驅動，方便寫進 shell script 或 CI。兩條路徑跑 graph 時都會把 LangGraph 的 agent 訊息透過 Rich panel 串流出來（prose 用 Markdown 渲染、tool 輸出做 JSON pretty-print、payload 過長會自動截斷）。`python -m tradingagents <subcommand>` 也走同一條 dispatcher。

#### 程式呼叫

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
    response_language="en-US",
)

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

`response_language` 是來自 `ResponseLanguage` `Literal` 的 BCP 47 tag（`zh-TW`、`zh-CN`、`en-US`、`ja-JP`、`ko-KR`、`de-DE`），挑最接近你希望 agent 用的語言即可。

`TradingAgentsGraph.propagate` 也接受一個可選的 `on_message` callback（`Callable[[AnyMessage], None]`），每收到一則 streamed LangGraph 訊息就會呼叫一次 — 想接自己的 renderer 時很好用，內建的 CLI / TUI 也是用這個 hook 來餵 Rich panel。

`llm_provider` 是 `langchain.chat_models.init_chat_model` 的 registry key（`openai`、`anthropic`、`google_genai`、`xai`、`openrouter`、`ollama`、`huggingface`、`litellm`)；`deep_think_llm` / `quick_think_llm` 則填該 provider 接受的 model name(`gpt-5`、`claude-sonnet-4-6`、`gemini-3-pro-preview`、`grok-4` 等）。

`response_language` 可控制所有 agent prompt 要求的回覆語言。沒有 exchange suffix 的 ticker 會自動透過 Yahoo Finance Search 解析。台股請直接傳股票代號，例如 `2330`、`2408`、`8069`；也支援明確的 Yahoo Finance symbol，例如 `2330.TW`、`8069.TWO`、`AAPL`、`TSM`。

```python
config = TradingAgentsConfig(
    llm_provider="openai",
    deep_think_llm="gpt-5",
    quick_think_llm="gpt-5-mini",
    max_debate_rounds=1,
    max_risk_discuss_rounds=1,
    max_recur_limit=100,
    response_language="zh-TW",
)

ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("2330", "2024-05-10")
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
    ├── interface/        # CLI / TUI 實作
    │   ├── cli.py        # fire 驅動的 flag runner（run_cli）
    │   ├── tui.py        # questionary 驅動的互動式 runner（run_tui）
    │   ├── display.py    # rich 版本的 LangChain message renderer
    │   └── help.py       # 取代 fire pager 的 rich help
    ├── llm.py            # Chat model 構造（init_chat_model wrapper + reasoning_effort mapping）
    ├── config.py         # TradingAgentsConfig schema 與全域 singleton
    ├── __init__.py       # Top-level public API（TradingAgentsConfig、TradingAgentsGraph）
    └── __main__.py       # Console script 入口（fire dispatcher 加 rich help）
```

## 🤖 Agent 工作流程

TradingAgents 透過 LangGraph `StateGraph` 編排 **12 個 LLM agent** 加上 **2 個支援元件**，每次執行會依序跑過 4 個 phase，所有狀態（各類 report、debate transcript、trade decision）都透過一個共用的 Pydantic `AgentState` 在所有節點之間傳遞。

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

每次執行的 log 會寫入 `results/<股票代碼>/`：`full_states_log_<股票代碼>_<日期>.json`、`conversation_log_<股票代碼>_<日期>.txt`、`conversation_log_<股票代碼>_<日期>.json`（base path 由 `TradingAgentsConfig.results_dir` 決定，預設為 `./results`）。

## 🤝 貢獻

有關開發說明（包含文件、測試和 Docker 服務等），請參閱 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 歡迎 Issue/PR
- 請遵循程式風格（ruff、型別）
- PR 標題遵循 Conventional Commits

## 📄 授權

MIT — 詳見 `LICENSE`。
