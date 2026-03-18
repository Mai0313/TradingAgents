# 系統架構與 Agents 盤點記錄

本文檔記錄 TradingAgents 的系統架構、資料獲取方式以及各 Agents 的職責與互動流程，供後續重構與其他 Agents 開發參考。

> **重構方向：** 未來計畫移除所有 LangGraph / LangChain 相關依賴，改用自建的 Agent 架構。本文檔確保在重構過程中，所有現有功能與流程都有完整的對照記錄。

---

## 目錄

1. [股市與外部資訊獲取方式 (Tools / Function Calling)](#1-股市與外部資訊獲取方式-tools--function-calling)
2. [資料路由機制 (Data Routing)](#2-資料路由機制-data-routing)
3. [所有 Agents 清單與詳細定義](#3-所有-agents-清單與詳細定義)
4. [LangGraph Workflow 完整流程](#4-langgraph-workflow-完整流程)
5. [共享狀態結構 (State Schema)](#5-共享狀態結構-state-schema)
6. [輔助元件 (Memory / Reflection / Signal Processing)](#6-輔助元件-memory--reflection--signal-processing)
7. [LLM 設定](#7-llm-設定)
8. [關鍵依賴清單 (待移除)](#8-關鍵依賴清單-待移除)

---

## 1. 股市與外部資訊獲取方式 (Tools / Function Calling)

目前股市、新聞、財報等資訊是透過 **LangChain `@tool` 裝飾器** 定義的 Function Calling 工具提供給 Analyst Agents 使用。所有工具定義在 `src/tradingagents/agents/utils/` 目錄下，統一透過 `agent_utils.py` 重新匯出。

### 1.1 工具總覽

共 **9 個** 工具，分為 4 大類別：

| # | 工具名稱 | 類別 | 定義檔案 | 行號 | 預設資料供應商 |
|---|---------|------|---------|------|--------------|
| 1 | `get_stock_data` | core_stock_apis | `agents/utils/core_stock_tools.py` | 8–24 | yfinance |
| 2 | `get_indicators` | technical_indicators | `agents/utils/technical_indicators_tools.py` | 8–26 | yfinance |
| 3 | `get_fundamentals` | fundamental_data | `agents/utils/fundamental_data_tools.py` | 8–22 | yfinance |
| 4 | `get_balance_sheet` | fundamental_data | `agents/utils/fundamental_data_tools.py` | 25–41 | yfinance |
| 5 | `get_cashflow` | fundamental_data | `agents/utils/fundamental_data_tools.py` | 44–60 | yfinance |
| 6 | `get_income_statement` | fundamental_data | `agents/utils/fundamental_data_tools.py` | 63–79 | yfinance |
| 7 | `get_news` | news_data | `agents/utils/news_data_tools.py` | 8–24 | yfinance |
| 8 | `get_global_news` | news_data | `agents/utils/news_data_tools.py` | 27–44 | yfinance |
| 9 | `get_insider_transactions` | news_data | `agents/utils/news_data_tools.py` | 47–57 | yfinance |

> 所有檔案路徑相對於 `src/tradingagents/`

### 1.2 各工具詳細參數

#### `get_stock_data` — 股價 OHLCV 數據
- **檔案:** `src/tradingagents/agents/utils/core_stock_tools.py` (L8–24)
- **參數:**
  - `symbol: str` — 股票代碼 (e.g. AAPL, TSM)
  - `start_date: str` — 開始日期 (yyyy-mm-dd)
  - `end_date: str` — 結束日期 (yyyy-mm-dd)
- **路由:** `route_to_vendor("get_stock_data", symbol, start_date, end_date)`

#### `get_indicators` — 技術分析指標
- **檔案:** `src/tradingagents/agents/utils/technical_indicators_tools.py` (L8–26)
- **參數:**
  - `symbol: str` — 股票代碼
  - `indicator: str` — 技術指標名稱
  - `curr_date: str` — 當前交易日期 (YYYY-mm-dd)
  - `look_back_days: int = 30` — 回顧天數
- **路由:** `route_to_vendor("get_indicators", symbol, indicator, curr_date, look_back_days)`

#### `get_fundamentals` — 公司基本面資料
- **檔案:** `src/tradingagents/agents/utils/fundamental_data_tools.py` (L8–22)
- **參數:**
  - `ticker: str` — 股票代碼
  - `curr_date: str` — 交易日期 (yyyy-mm-dd)
- **路由:** `route_to_vendor("get_fundamentals", ticker, curr_date)`

#### `get_balance_sheet` — 資產負債表
- **檔案:** `src/tradingagents/agents/utils/fundamental_data_tools.py` (L25–41)
- **參數:**
  - `ticker: str` — 股票代碼
  - `freq: str = "quarterly"` — 頻率 (annual / quarterly)
  - `curr_date: str = None` — 交易日期
- **路由:** `route_to_vendor("get_balance_sheet", ticker, freq, curr_date)`

#### `get_cashflow` — 現金流量表
- **檔案:** `src/tradingagents/agents/utils/fundamental_data_tools.py` (L44–60)
- **參數:** 同 `get_balance_sheet`
- **路由:** `route_to_vendor("get_cashflow", ticker, freq, curr_date)`

#### `get_income_statement` — 損益表
- **檔案:** `src/tradingagents/agents/utils/fundamental_data_tools.py` (L63–79)
- **參數:** 同 `get_balance_sheet`
- **路由:** `route_to_vendor("get_income_statement", ticker, freq, curr_date)`

#### `get_news` — 公司相關新聞
- **檔案:** `src/tradingagents/agents/utils/news_data_tools.py` (L8–24)
- **參數:**
  - `ticker: str` — 股票代碼
  - `start_date: str` — 開始日期 (yyyy-mm-dd)
  - `end_date: str` — 結束日期 (yyyy-mm-dd)
- **路由:** `route_to_vendor("get_news", ticker, start_date, end_date)`

#### `get_global_news` — 全球總經新聞
- **檔案:** `src/tradingagents/agents/utils/news_data_tools.py` (L27–44)
- **參數:**
  - `curr_date: str` — 當前日期 (yyyy-mm-dd)
  - `look_back_days: int = 7` — 回顧天數
  - `limit: int = 5` — 最大文章數
- **路由:** `route_to_vendor("get_global_news", curr_date, look_back_days, limit)`

#### `get_insider_transactions` — 內部人員交易
- **檔案:** `src/tradingagents/agents/utils/news_data_tools.py` (L47–57)
- **參數:**
  - `ticker: str` — 股票代碼
- **路由:** `route_to_vendor("get_insider_transactions", ticker)`

### 1.3 工具匯出入口

- **檔案:** `src/tradingagents/agents/utils/agent_utils.py` (L1–50)
- 統一從各工具模組 re-export 所有 9 個工具函式
- 另外定義 `create_msg_delete()` (L36–49)：建立一個清除對話歷史的函式，用於 Analyst 之間的狀態傳遞

### 1.4 工具與 Analyst 的綁定關係

| Analyst | 綁定的 Tools | ToolNode 名稱 |
|---------|-------------|--------------|
| Market Analyst | `get_stock_data`, `get_indicators` | `tools_market` |
| Social Media Analyst | `get_news` | `tools_social` |
| News Analyst | `get_news`, `get_global_news`, `get_insider_transactions` | `tools_news` |
| Fundamentals Analyst | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | `tools_fundamentals` |

綁定方式：
- 各 Analyst 建立函式中透過 `llm.bind_tools(tools)` 將工具綁定到 LLM
- 在 `TradingAgentsGraph._create_tool_nodes()` (L146–172 of `graph/trading_graph.py`) 中建立 LangGraph 的 `ToolNode` 包裝

---

## 2. 資料路由機制 (Data Routing)

所有工具函式內部都呼叫 `route_to_vendor()` 進行資料路由，支援多供應商自動切換。

### 2.1 架構概覽

```
Tool Function (@tool) ──► route_to_vendor() ──► Vendor Implementation
                              │
                              ├── get_category_for_method()  // 查找工具所屬類別
                              ├── get_vendor()               // 從 config 取得供應商
                              └── VENDOR_METHODS[method]     // 找到對應實作函式
```

### 2.2 核心檔案

| 檔案 | 用途 | 關鍵內容 |
|------|------|---------|
| `dataflows/interface.py` | 路由核心 | `TOOLS_CATEGORIES` (L25–39), `VENDOR_METHODS` (L44–79), `route_to_vendor()` (L109–137) |
| `dataflows/config.py` | 設定管理 | `initialize_config()` (L16–19), `set_config()` (L22–29), `get_config()` (L32–39) |
| `default_config.py` | 預設設定 | `data_vendors` (L23–28), `tool_vendors` (L30–32) |

### 2.3 供應商對照表

| 工具 | yfinance 實作 | alpha_vantage 實作 |
|------|--------------|-------------------|
| `get_stock_data` | `y_finance.get_yfin_data_online` | `alpha_vantage.get_stock` |
| `get_indicators` | `y_finance.get_stock_stats_indicators_window` | `alpha_vantage.get_indicator` |
| `get_fundamentals` | `y_finance.get_fundamentals` | `alpha_vantage.get_fundamentals` |
| `get_balance_sheet` | `y_finance.get_balance_sheet` | `alpha_vantage.get_balance_sheet` |
| `get_cashflow` | `y_finance.get_cashflow` | `alpha_vantage.get_cashflow` |
| `get_income_statement` | `y_finance.get_income_statement` | `alpha_vantage.get_income_statement` |
| `get_news` | `yfinance_news.get_news_yfinance` | `alpha_vantage.get_news` |
| `get_global_news` | `yfinance_news.get_global_news_yfinance` | `alpha_vantage.get_global_news` |
| `get_insider_transactions` | `y_finance.get_insider_transactions` | `alpha_vantage.get_insider_transactions` |

### 2.4 供應商實作檔案

| 檔案 | 用途 |
|------|------|
| `dataflows/y_finance.py` | yfinance 股價、基本面、內部交易 |
| `dataflows/yfinance_news.py` | yfinance 新聞 |
| `dataflows/stockstats_utils.py` | 技術指標計算 (被 y_finance 使用) |
| `dataflows/alpha_vantage.py` | Alpha Vantage 主入口 |
| `dataflows/alpha_vantage_stock.py` | Alpha Vantage 股價 |
| `dataflows/alpha_vantage_news.py` | Alpha Vantage 新聞 |
| `dataflows/alpha_vantage_fundamentals.py` | Alpha Vantage 基本面 |
| `dataflows/alpha_vantage_indicator.py` | Alpha Vantage 技術指標 |
| `dataflows/alpha_vantage_common.py` | Alpha Vantage 共用 (含 `AlphaVantageRateLimitError`) |
| `dataflows/utils.py` | 共用工具函式 |

### 2.5 Fallback 機制

`route_to_vendor()` (interface.py L109–137) 實作了自動 fallback：
1. 優先使用設定的主要供應商
2. 若遇到 `AlphaVantageRateLimitError` 則自動切換至下一個可用供應商
3. 支援 config 中以逗號分隔多個供應商作為 fallback 鏈

---

## 3. 所有 Agents 清單與詳細定義

### 3.1 Agent 角色分類

系統共有 **12 個** Agent 角色 + **2 個** 輔助元件：

| 分類 | Agent | 使用 Tools | LLM 等級 |
|------|-------|-----------|---------|
| **分析師** | Market Analyst | `get_stock_data`, `get_indicators` | quick |
| **分析師** | Social Media Analyst | `get_news` | quick |
| **分析師** | News Analyst | `get_news`, `get_global_news`, `get_insider_transactions` | quick |
| **分析師** | Fundamentals Analyst | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | quick |
| **研究員** | Bull Researcher | 無 | quick |
| **研究員** | Bear Researcher | 無 | quick |
| **經理** | Research Manager (投資裁判) | 無 | deep |
| **交易員** | Trader | 無 | quick |
| **風控辯論** | Aggressive Debator | 無 | quick |
| **風控辯論** | Conservative Debator | 無 | quick |
| **風控辯論** | Neutral Debator | 無 | quick |
| **經理** | Risk Manager (風險裁判) | 無 | deep |
| *輔助* | *Reflector* | *無* | *quick* |
| *輔助* | *SignalProcessor* | *無* | *quick* |

### 3.2 各 Agent 詳細定義

#### Market Analyst — 市場技術分析師

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/analysts/market_analyst.py` |
| **建立函式** | `create_market_analyst(llm: BaseChatModel)` (L10–73) |
| **LLM** | `quick_thinking_llm` + `bind_tools([get_stock_data, get_indicators])` |
| **Prompt 位置** | 同檔案 L18–55 (inline) |
| **職責** | 從最多 8 個互補技術指標中選擇分析，必須先呼叫 `get_stock_data` 再呼叫 `get_indicators`，產出詳細市場報告含 Markdown 表格 |
| **可用指標** | close_50_sma, close_200_sma, close_10_ema, macd, macds, macdh, rsi_14, boll, boll_ub, boll_lb, atr_14, vwma |
| **輸出** | 寫入 `state["market_report"]` |

#### Social Media Analyst — 社群情緒分析師

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/analysts/social_media_analyst.py` |
| **建立函式** | `create_social_media_analyst(llm: BaseChatModel)` (L10–52) |
| **LLM** | `quick_thinking_llm` + `bind_tools([get_news])` |
| **Prompt 位置** | 同檔案 L17–19 (inline) |
| **職責** | 分析公司相關社群媒體與新聞的情緒傾向，產出含情緒評估的報告與 Markdown 表格 |
| **輸出** | 寫入 `state["sentiment_report"]` |

#### News Analyst — 新聞分析師

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/analysts/news_analyst.py` |
| **建立函式** | `create_news_analyst(llm: BaseChatModel)` (L10–52) |
| **LLM** | `quick_thinking_llm` + `bind_tools([get_news, get_global_news])` |
| **Prompt 位置** | 同檔案 L17–19 (inline) |
| **職責** | 分析公司新聞與全球總經新聞，產出交易導向的新聞報告與 Markdown 表格 |
| **輸出** | 寫入 `state["news_report"]` |

#### Fundamentals Analyst — 基本面分析師

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/analysts/fundamentals_analyst.py` |
| **建立函式** | `create_fundamentals_analyst(llm: BaseChatModel)` (L15–59) |
| **LLM** | `quick_thinking_llm` + `bind_tools([get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement])` |
| **Prompt 位置** | 同檔案 L21–25 (inline) |
| **職責** | 分析財報、資產負債表、現金流、損益表，產出基本面報告與 Markdown 表格 |
| **輸出** | 寫入 `state["fundamentals_report"]` |

#### Bull Researcher — 看多研究員

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/researchers/bull_researcher.py` |
| **建立函式** | `create_bull_researcher(llm: BaseChatModel, memory: FinancialSituationMemory)` (L9–63) |
| **LLM** | `quick_thinking_llm` (無 tool binding) |
| **Prompt 位置** | 同檔案 L29–47 (inline template) |
| **輸入** | `market_report`, `sentiment_report`, `news_report`, `fundamentals_report`, 辯論歷史, 上一個 Bear 論點, 記憶 |
| **職責** | 提出看多論點：成長潛力、競爭優勢、正向指標，並反駁 Bear 的觀點 |
| **輸出** | 更新 `investment_debate_state` |

#### Bear Researcher — 看空研究員

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/researchers/bear_researcher.py` |
| **建立函式** | `create_bear_researcher(llm: BaseChatModel, memory: FinancialSituationMemory)` (L9–65) |
| **LLM** | `quick_thinking_llm` (無 tool binding) |
| **Prompt 位置** | 同檔案 L29–48 (inline template) |
| **輸入** | 同 Bull Researcher，但接收上一個 Bull 論點 |
| **職責** | 提出看空論點：風險、競爭劣勢、負面指標，並反駁 Bull 的觀點 |
| **輸出** | 更新 `investment_debate_state` |

#### Research Manager — 投資裁判

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/managers/research_manager.py` |
| **建立函式** | `create_research_manager(llm: BaseChatModel, memory: FinancialSituationMemory)` (L9–62) |
| **LLM** | `deep_thinking_llm` (無 tool binding) |
| **Prompt 位置** | 同檔案 L27–45 (inline template) |
| **輸入** | 辯論歷史、過去反思記憶 |
| **職責** | 評判 Bull/Bear 辯論，決定 Buy/Sell/Hold，產出投資計畫 |
| **輸出** | 寫入 `state["investment_plan"]`, 更新 `investment_debate_state["judge_decision"]` |

#### Trader — 交易員

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/trader/trader.py` |
| **建立函式** | `create_trader(llm: BaseChatModel, memory: FinancialSituationMemory)` (L10–47) |
| **LLM** | `quick_thinking_llm` (無 tool binding) |
| **Prompt 位置** | 同檔案 L37–39 (inline) |
| **輸入** | `investment_plan`, 過去反思記憶 |
| **職責** | 根據投資計畫制定交易方案，必須以 `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**` 結尾 |
| **輸出** | 寫入 `state["trader_investment_plan"]` |

#### Aggressive Debator — 激進型風險辯論者

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/risk_mgmt/aggressive_debator.py` |
| **建立函式** | `create_aggressive_debator(llm: BaseChatModel)` (L7–57) |
| **LLM** | `quick_thinking_llm` (無 tool binding) |
| **Prompt 位置** | 同檔案 L22–34 (inline template) |
| **輸入** | `trader_investment_plan`, 四份分析報告, 辯論歷史, 最近 Conservative/Neutral 回應 |
| **職責** | 從高風險高報酬角度分析，強調上漲潛力、成長與創新機會 |
| **輸出** | 更新 `risk_debate_state` |

#### Conservative Debator — 保守型風險辯論者

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/risk_mgmt/conservative_debator.py` |
| **建立函式** | `create_conservative_debator(llm: BaseChatModel)` (L7–56) |
| **LLM** | `quick_thinking_llm` (無 tool binding) |
| **Prompt 位置** | 同檔案 L22–34 (inline template) |
| **輸入** | 同 Aggressive，但接收最近 Aggressive/Neutral 回應 |
| **職責** | 從資產保護角度分析，強調降低波動、確保穩健增長 |
| **輸出** | 更新 `risk_debate_state` |

#### Neutral Debator — 中立型風險辯論者

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/risk_mgmt/neutral_debator.py` |
| **建立函式** | `create_neutral_debator(llm: BaseChatModel)` (L7–58) |
| **LLM** | `quick_thinking_llm` (無 tool binding) |
| **Prompt 位置** | 同檔案 L22–34 (inline template) |
| **輸入** | 同 Aggressive，但接收最近 Aggressive/Conservative 回應 |
| **職責** | 平衡看待風險與收益，同時挑戰激進與保守觀點 |
| **輸出** | 更新 `risk_debate_state` |

#### Risk Manager — 風險裁判

| 項目 | 內容 |
|------|------|
| **定義檔案** | `src/tradingagents/agents/managers/risk_manager.py` |
| **建立函式** | `create_risk_manager(llm: BaseChatModel, memory: FinancialSituationMemory)` (L9–69) |
| **LLM** | `deep_thinking_llm` (無 tool binding) |
| **Prompt 位置** | 同檔案 L27–46 (inline template) |
| **輸入** | 風險辯論歷史、過去反思記憶 |
| **職責** | 評判三方風險辯論，修正交易員計畫，做出最終 Buy/Sell/Hold 決策 |
| **輸出** | 寫入 `state["final_trade_decision"]`, 更新 `risk_debate_state["judge_decision"]` |

### 3.3 重要備註

- **所有 Prompt 目前都是 inline 定義**，沒有獨立的 prompt 檔案目錄
- 只有 4 個 **Analyst** 使用 Tools (Function Calling)，其餘 Agent 都是純 LLM 推理
- **Bull/Bear/Trader/Research Manager/Risk Manager** 使用 `FinancialSituationMemory` 進行記憶檢索
- **Aggressive/Conservative/Neutral Debator** 不使用記憶

---

## 4. LangGraph Workflow 完整流程

### 4.1 核心檔案

| 檔案 | 用途 |
|------|------|
| `src/tradingagents/graph/trading_graph.py` | `TradingAgentsGraph` 主類別，初始化 LLM、Memory、ToolNode，編譯 Graph |
| `src/tradingagents/graph/setup.py` | `GraphSetup` 類別，定義所有節點與邊 |
| `src/tradingagents/graph/conditional_logic.py` | `ConditionalLogic` 類別，定義條件路由邏輯 |
| `src/tradingagents/graph/propagation.py` | `Propagator` 類別，建立初始狀態 |
| `src/tradingagents/graph/reflection.py` | `Reflector` 類別，交易後反思與記憶更新 |
| `src/tradingagents/graph/signal_processing.py` | `SignalProcessor` 類別，從文字中提取 BUY/SELL/HOLD |

### 4.2 Graph 節點清單

定義於 `src/tradingagents/graph/setup.py` `setup_graph()` 方法 (L109–200)：

| 節點名稱 | 處理函式 | 行號 | 說明 |
|----------|---------|------|------|
| `Market Analyst` | `create_market_analyst(quick_thinking_llm)` | L144 | 市場分析 |
| `tools_market` | `ToolNode([get_stock_data, get_indicators])` | L147 | 市場工具執行 |
| `Msg Clear Market` | `create_msg_delete()` | L146 | 清理對話歷史 |
| `Social Analyst` | `create_social_media_analyst(quick_thinking_llm)` | L144 | 社群分析 |
| `tools_social` | `ToolNode([get_news])` | L147 | 社群工具執行 |
| `Msg Clear Social` | `create_msg_delete()` | L146 | 清理對話歷史 |
| `News Analyst` | `create_news_analyst(quick_thinking_llm)` | L144 | 新聞分析 |
| `tools_news` | `ToolNode([get_news, get_global_news, get_insider_transactions])` | L147 | 新聞工具執行 |
| `Msg Clear News` | `create_msg_delete()` | L146 | 清理對話歷史 |
| `Fundamentals Analyst` | `create_fundamentals_analyst(quick_thinking_llm)` | L144 | 基本面分析 |
| `tools_fundamentals` | `ToolNode([get_fundamentals, ...])` | L147 | 基本面工具執行 |
| `Msg Clear Fundamentals` | `create_msg_delete()` | L146 | 清理對話歷史 |
| `Bull Researcher` | `create_bull_researcher(quick_thinking_llm, bull_memory)` | L150 | 看多辯論 |
| `Bear Researcher` | `create_bear_researcher(quick_thinking_llm, bear_memory)` | L151 | 看空辯論 |
| `Research Manager` | `create_research_manager(deep_thinking_llm, invest_judge_memory)` | L152 | 投資裁判 |
| `Trader` | `create_trader(quick_thinking_llm, trader_memory)` | L153 | 交易決策 |
| `Aggressive Analyst` | `create_aggressive_debator(quick_thinking_llm)` | L154 | 激進風控 |
| `Neutral Analyst` | `create_neutral_debator(quick_thinking_llm)` | L155 | 中立風控 |
| `Conservative Analyst` | `create_conservative_debator(quick_thinking_llm)` | L156 | 保守風控 |
| `Risk Judge` | `create_risk_manager(deep_thinking_llm, risk_manager_memory)` | L157 | 風險裁判 |

### 4.3 邊 (Edges) 定義

#### 固定邊 (Unconditional)

| 起點 | 終點 | 位置 |
|------|------|------|
| `START` | 第一個 Analyst (預設 `Market Analyst`) | setup.py L161 |
| `tools_{analyst}` | `{Analyst} Analyst` (回到同一 Analyst 繼續) | setup.py L101 |
| `Msg Clear {Analyst}` | 下一個 Analyst 或 `Bull Researcher` (最後一個) | setup.py L105, L107 |
| `Research Manager` | `Trader` | setup.py L177 |
| `Trader` | `Aggressive Analyst` | setup.py L178 |
| `Risk Judge` | `END` | setup.py L197 |

#### 條件邊 (Conditional) — 定義於 `conditional_logic.py`

**Analyst 工具迴圈** (L14–44)：
```
{Analyst} ──► should_continue_{type}() ──► tools_{type}     (若有 tool_calls)
                                       └──► Msg Clear {Type} (若無 tool_calls，分析完成)
```

**投資辯論迴圈** (L46–54)：
```
Bull Researcher ──► should_continue_debate() ──► Bear Researcher    (Bull 發言後)
                                              └──► Research Manager  (達到 max_debate_rounds)

Bear Researcher ──► should_continue_debate() ──► Bull Researcher    (Bear 發言後)
                                              └──► Research Manager  (達到 max_debate_rounds)
```
- 終止條件：`count >= 2 * max_debate_rounds` (預設 max_debate_rounds=1，即各一輪)

**風險辯論迴圈** (L56–66)：
```
Aggressive  ──► should_continue_risk_analysis() ──► Conservative  (Aggressive 發言後)
                                                 └──► Risk Judge   (達到 max_risk_discuss_rounds)

Conservative ──► should_continue_risk_analysis() ──► Neutral       (Conservative 發言後)
                                                  └──► Risk Judge   (達到 max_risk_discuss_rounds)

Neutral ──► should_continue_risk_analysis() ──► Aggressive    (Neutral 發言後)
                                             └──► Risk Judge   (達到 max_risk_discuss_rounds)
```
- 終止條件：`count >= 3 * max_risk_discuss_rounds` (預設 max_risk_discuss_rounds=1，即各一輪)
- 輪換順序：Aggressive → Conservative → Neutral → Aggressive → ...

### 4.4 完整流程圖

```
START
  │
  ▼
┌─────────────────── 第一階段：資料收集與分析 ───────────────────┐
│                                                                │
│  Market Analyst ◄──► tools_market (迴圈至無 tool_calls)        │
│       │                                                        │
│       ▼                                                        │
│  Msg Clear Market                                              │
│       │                                                        │
│       ▼                                                        │
│  Social Analyst ◄──► tools_social                              │
│       │                                                        │
│       ▼                                                        │
│  Msg Clear Social                                              │
│       │                                                        │
│       ▼                                                        │
│  News Analyst ◄──► tools_news                                  │
│       │                                                        │
│       ▼                                                        │
│  Msg Clear News                                                │
│       │                                                        │
│       ▼                                                        │
│  Fundamentals Analyst ◄──► tools_fundamentals                  │
│       │                                                        │
│       ▼                                                        │
│  Msg Clear Fundamentals                                        │
│                                                                │
└────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────── 第二階段：投資研究辯論 ─────────────────────┐
│                                                                │
│  Bull Researcher ◄─────── 辯論迴圈 ───────► Bear Researcher   │
│                     (max_debate_rounds 輪)                     │
│                           │                                    │
│                           ▼                                    │
│                   Research Manager                              │
│                  (產出投資計畫)                                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────── 第三階段：交易決策 ────────────────────────┐
│                                                                │
│                       Trader                                   │
│                (制定交易方案)                                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────── 第四階段：風險控管辯論 ────────────────────┐
│                                                                │
│  Aggressive ──► Conservative ──► Neutral ──► (迴圈)           │
│                (max_risk_discuss_rounds 輪)                    │
│                           │                                    │
│                           ▼                                    │
│                      Risk Judge                                │
│                  (最終交易決策)                                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
        │
        ▼
       END
```

### 4.5 Graph 編譯與執行入口

- **主類別:** `TradingAgentsGraph` (`src/tradingagents/graph/trading_graph.py` L34–261)
- **初始化:** `__init__()` (L37–127) — 建立 LLM clients、Memory、ToolNodes、ConditionalLogic，編譯 Graph
- **執行:** `propagate(company_name, trade_date)` (L174–204) — 建立初始狀態並執行 Graph
- **反思:** `reflect_and_remember(returns_losses)` (L245–257) — 交易後反思
- **信號提取:** `process_signal(full_signal)` (L259–261) — 提取 BUY/SELL/HOLD

---

## 5. 共享狀態結構 (State Schema)

定義於 `src/tradingagents/agents/utils/agent_states.py`。

### `AgentState` (L41–63) — 主狀態，繼承 `MessagesState`

| 欄位 | 型別 | 說明 | 寫入者 |
|------|------|------|--------|
| `messages` | `list[BaseMessage]` | 對話歷史 (繼承自 MessagesState) | 所有 Agent |
| `company_of_interest` | `str` | 交易標的公司名稱 | 初始化 |
| `trade_date` | `str` | 交易日期 | 初始化 |
| `sender` | `str` | 發送訊息的 Agent 名稱 | 所有 Agent |
| `market_report` | `str` | 市場分析報告 | Market Analyst |
| `sentiment_report` | `str` | 社群情緒報告 | Social Media Analyst |
| `news_report` | `str` | 新聞分析報告 | News Analyst |
| `fundamentals_report` | `str` | 基本面報告 | Fundamentals Analyst |
| `investment_debate_state` | `InvestDebateState` | 投資辯論狀態 | Bull/Bear/Research Manager |
| `investment_plan` | `str` | 投資計畫 | Research Manager |
| `trader_investment_plan` | `str` | 交易方案 | Trader |
| `risk_debate_state` | `RiskDebateState` | 風險辯論狀態 | Aggressive/Conservative/Neutral/Risk Judge |
| `final_trade_decision` | `str` | 最終交易決策 | Risk Judge |

### `InvestDebateState` (L8–14)

| 欄位 | 型別 | 說明 |
|------|------|------|
| `bull_history` | `str` | Bull 辯論歷史 |
| `bear_history` | `str` | Bear 辯論歷史 |
| `history` | `str` | 完整辯論歷史 |
| `current_response` | `str` | 最新回應 |
| `judge_decision` | `str` | 裁判決策 |
| `count` | `int` | 辯論回合計數 |

### `RiskDebateState` (L18–38)

| 欄位 | 型別 | 說明 |
|------|------|------|
| `aggressive_history` | `str` | Aggressive 辯論歷史 |
| `conservative_history` | `str` | Conservative 辯論歷史 |
| `neutral_history` | `str` | Neutral 辯論歷史 |
| `history` | `str` | 完整辯論歷史 |
| `latest_speaker` | `str` | 最近發言者 |
| `current_aggressive_response` | `str` | Aggressive 最新回應 |
| `current_conservative_response` | `str` | Conservative 最新回應 |
| `current_neutral_response` | `str` | Neutral 最新回應 |
| `judge_decision` | `str` | 裁判決策 |
| `count` | `int` | 辯論回合計數 |

---

## 6. 輔助元件 (Memory / Reflection / Signal Processing)

### 6.1 FinancialSituationMemory — 記憶系統

- **檔案:** `src/tradingagents/agents/utils/memory.py` (L12–98)
- **演算法:** BM25Okapi (lexical similarity，無需 API)
- **儲存:** 記憶 `(situation, recommendation)` pairs
- **檢索:** `get_memories(current_situation, n_matches)` 回傳最相似的過往經驗
- **共有 5 個實例:** bull_memory, bear_memory, trader_memory, invest_judge_memory, risk_manager_memory

### 6.2 Reflector — 反思系統

- **檔案:** `src/tradingagents/graph/reflection.py` (L10–143)
- **用途:** 交易後根據實際損益反思每個 Agent 的決策品質，更新對應記憶
- **觸發:** 呼叫 `TradingAgentsGraph.reflect_and_remember(returns_losses)` 後依序反思：
  1. Bull Researcher (L76–87)
  2. Bear Researcher (L89–100)
  3. Trader (L102–113)
  4. Invest Judge (L115–128)
  5. Risk Manager (L130–143)

### 6.3 SignalProcessor — 信號提取

- **檔案:** `src/tradingagents/graph/signal_processing.py` (L6–30)
- **用途:** 從 Risk Judge 的自然語言決策文本中提取 BUY/SELL/HOLD
- **方法:** 使用 LLM 做文字提取

---

## 7. LLM 設定

### 7.1 設定位置

- **預設設定:** `src/tradingagents/default_config.py` (L1–33)
- **LLM 工廠:** `src/tradingagents/llm_clients/factory.py` — `create_llm_client()` (L7–38)

### 7.2 LLM 等級分配

| 變數 | Config Key | 預設模型 | 用途 |
|------|-----------|---------|------|
| `quick_thinking_llm` | `quick_think_llm` | `gpt-5-mini` | 所有 Analyst、Researcher、Trader、Debator、Reflector、SignalProcessor |
| `deep_thinking_llm` | `deep_think_llm` | `gpt-5.2` | Research Manager、Risk Manager |

### 7.3 支援的 LLM Provider

| Provider | 設定值 | Client 類別 |
|----------|--------|-------------|
| OpenAI | `openai` | `OpenAIClient` |
| Anthropic | `anthropic` | `AnthropicClient` |
| Google | `google` | `GoogleClient` |
| xAI | `xai` | `OpenAIClient` (相容 API) |
| Ollama | `ollama` | `OpenAIClient` (相容 API) |
| OpenRouter | `openrouter` | `OpenAIClient` (相容 API) |

---

## 8. 關鍵依賴清單 (待移除)

以下為未來重構時需要替換或移除的 LangGraph/LangChain 相關依賴：

| 依賴 | 用途 | 影響範圍 |
|------|------|---------|
| `langgraph` | Graph 建構、`StateGraph`、`ToolNode`、`CompiledStateGraph` | `graph/setup.py`, `graph/trading_graph.py` |
| `langchain_core` | `BaseChatModel`, `@tool` 裝飾器, `MessagesState`, `HumanMessage`, `RemoveMessage` | 所有 Agent 定義, `agent_states.py`, `agent_utils.py` |
| `langchain_openai` | `ChatOpenAI` (在 signal_processing.py 的 type hint 中使用) | `graph/signal_processing.py` |
| `langchain_anthropic` | Anthropic LLM Client | `llm_clients/anthropic_client.py` |
| `langchain_google_genai` | Google LLM Client | `llm_clients/google_client.py` |

重構時需自建的核心元件：
1. **Tool Calling 機制** — 替代 `@tool` 裝飾器與 `ToolNode`
2. **Graph / Workflow 引擎** — 替代 `StateGraph` 的節點、邊、條件分支
3. **State 管理** — 替代 `MessagesState` 與 `TypedDict` 狀態傳遞
4. **LLM Client 抽象** — 替代 `BaseChatModel` 的統一介面 (目前 `llm_clients/` 已有一定程度的抽象)
