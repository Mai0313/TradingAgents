# System Architecture and Agent Inventory

This document records the TradingAgents system architecture, data acquisition methods, and the responsibilities and interaction flows of each agent. It is intended as the single source of truth for the runtime behavior of the framework and as a reference for future refactoring work.

> **Refactoring direction:** The long-term plan is to remove the LangGraph / LangChain runtime dependency and replace it with a custom-built agent orchestrator. This document captures every feature, tool, and workflow that must remain intact during that migration.

---

## Table of Contents

1. [Market Data and External Information Access (Tools / Function Calling)](#1-market-data-and-external-information-access-tools--function-calling)
2. [Data Acquisition Layer](#2-data-acquisition-layer)
3. [Complete Agent List and Detailed Definitions](#3-complete-agent-list-and-detailed-definitions)
4. [Complete LangGraph Workflow](#4-complete-langgraph-workflow)
5. [Shared State Structure (State Schema)](#5-shared-state-structure-state-schema)
6. [Supporting Components (Memory / Reflection / Signal Processing)](#6-supporting-components-memory--reflection--signal-processing)
7. [LLM Configuration](#7-llm-configuration)
8. [Key Dependency List (To Be Removed)](#8-key-dependency-list-to-be-removed)

---

## 1. Market Data and External Information Access (Tools / Function Calling)

Market data, news, financial statements, and related information are exposed to analyst agents through Function Calling tools declared with the **LangChain `@tool` decorator**. All tool definitions live under `src/tradingagents/agents/utils/` and are re-exported centrally through `agent_utils.py`.

### 1.1 Tool Overview

There are **9** tools in total, grouped into 4 categories. Every tool is ultimately backed by `yfinance`.

| #   | Tool Name                  | Category             | Definition File                              |
| --- | -------------------------- | -------------------- | -------------------------------------------- |
| 1   | `get_stock_data`           | core_stock_apis      | `agents/utils/core_stock_tools.py`           |
| 2   | `get_indicators`           | technical_indicators | `agents/utils/technical_indicators_tools.py` |
| 3   | `get_fundamentals`         | fundamental_data     | `agents/utils/fundamental_data_tools.py`     |
| 4   | `get_balance_sheet`        | fundamental_data     | `agents/utils/fundamental_data_tools.py`     |
| 5   | `get_cashflow`             | fundamental_data     | `agents/utils/fundamental_data_tools.py`     |
| 6   | `get_income_statement`     | fundamental_data     | `agents/utils/fundamental_data_tools.py`     |
| 7   | `get_news`                 | news_data            | `agents/utils/news_data_tools.py`            |
| 8   | `get_global_news`          | news_data            | `agents/utils/news_data_tools.py`            |
| 9   | `get_insider_transactions` | news_data            | `agents/utils/news_data_tools.py`            |

> All file paths are relative to `src/tradingagents/`.

### 1.2 Detailed Parameters for Each Tool

#### `get_stock_data` - Stock OHLCV data

- **File:** `agents/utils/core_stock_tools.py`
- **Parameters:**
    - `symbol: str` - Stock ticker symbol (e.g. AAPL, TSM)
    - `start_date: str` - Start date (`yyyy-mm-dd`)
    - `end_date: str` - End date (`yyyy-mm-dd`)
- **Backend:** `y_finance.get_yfin_data_online`

#### `get_indicators` - Technical analysis indicators

- **File:** `agents/utils/technical_indicators_tools.py`
- **Parameters:**
    - `symbol: str` - Stock ticker symbol
    - `indicator: str` - Technical indicator name
    - `curr_date: str` - Current trading date (`YYYY-mm-dd`)
    - `look_back_days: int = 30` - Look-back window in days
- **Backend:** `y_finance.get_stock_stats_indicators_window`

#### `get_fundamentals` - Company fundamentals data

- **File:** `agents/utils/fundamental_data_tools.py`
- **Parameters:**
    - `ticker: str` - Stock ticker symbol
    - `curr_date: str` - Trading date (`yyyy-mm-dd`)
- **Backend:** `y_finance.get_fundamentals`

#### `get_balance_sheet` - Balance sheet

- **File:** `agents/utils/fundamental_data_tools.py`
- **Parameters:**
    - `ticker: str` - Stock ticker symbol
    - `freq: str = "quarterly"` - Reporting frequency (`annual` / `quarterly`)
    - `curr_date: str | None = None` - Optional trading date (unused by the yfinance backend)
- **Backend:** `y_finance.get_balance_sheet`

#### `get_cashflow` - Cash flow statement

- **File:** `agents/utils/fundamental_data_tools.py`
- **Parameters:** Same as `get_balance_sheet`
- **Backend:** `y_finance.get_cashflow`

#### `get_income_statement` - Income statement

- **File:** `agents/utils/fundamental_data_tools.py`
- **Parameters:** Same as `get_balance_sheet`
- **Backend:** `y_finance.get_income_statement`

#### `get_news` - Company-related news

- **File:** `agents/utils/news_data_tools.py`
- **Parameters:**
    - `ticker: str` - Stock ticker symbol
    - `start_date: str` - Start date (`yyyy-mm-dd`)
    - `end_date: str` - End date (`yyyy-mm-dd`)
- **Backend:** `yfinance_news.get_news_yfinance`

#### `get_global_news` - Global macro news

- **File:** `agents/utils/news_data_tools.py`
- **Parameters:**
    - `curr_date: str` - Current date (`yyyy-mm-dd`)
    - `look_back_days: int = 7` - Look-back window in days
    - `limit: int = 5` - Maximum number of articles
- **Backend:** `yfinance_news.get_global_news_yfinance`

#### `get_insider_transactions` - Insider transactions

- **File:** `agents/utils/news_data_tools.py`
- **Parameters:**
    - `ticker: str` - Stock ticker symbol
- **Backend:** `y_finance.get_insider_transactions`

### 1.3 Tool Export Entry Point

- **File:** `agents/utils/agent_utils.py`
- Re-exports all 9 `@tool` functions from their individual modules so that agents can import them from a single location.
- Also defines `create_msg_delete()`, a factory that returns a LangGraph node used to clear the `messages` history between analysts. It emits `RemoveMessage` entries for every existing message and appends a `HumanMessage("Continue")` placeholder so that providers that require a trailing human message (e.g. Anthropic) do not choke on an empty message list.

### 1.4 Tool-to-Analyst Binding

The LLM-side binding (i.e. what the analyst is allowed to *call*) is defined inside each analyst factory in `agents/analysts/*.py`. The execution-side wrapper (i.e. what the `ToolNode` is willing to *run*) is configured inside `TradingAgentsGraph.tool_nodes` in `graph/trading_graph.py`.

| Analyst              | LLM-Bound Tools (what the agent may call)                                       | ToolNode Name        | ToolNode Contents                                         |
| -------------------- | ------------------------------------------------------------------------------- | -------------------- | --------------------------------------------------------- |
| Market Analyst       | `get_stock_data`, `get_indicators`                                              | `tools_market`       | `get_stock_data`, `get_indicators`                        |
| Social Media Analyst | `get_news`                                                                      | `tools_social`       | `get_news`                                                |
| News Analyst         | `get_news`, `get_global_news`                                                   | `tools_news`         | `get_news`, `get_global_news`, `get_insider_transactions` |
| Fundamentals Analyst | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | `tools_fundamentals` | Same as LLM binding                                       |

> **Note:** `tools_news` currently exposes `get_insider_transactions`, but the News Analyst LLM is not bound to that tool, so it can never be invoked from the graph today. This is effectively dead wiring kept in `TradingAgentsGraph.tool_nodes` and should be cleaned up (either drop the tool from the ToolNode or bind it on the News Analyst).

Binding mechanism:

- Each analyst factory wraps the LLM with `llm.bind_tools(tools)` inside `ChatPromptTemplate | llm.bind_tools(...)` chains.
- `TradingAgentsGraph.tool_nodes` is a `@computed_field` / `cached_property` returning `dict[str, ToolNode]` keyed by analyst type (`market`, `social`, `news`, `fundamentals`).

---

## 2. Data Acquisition Layer

All market data, fundamentals, and news are fetched through `yfinance`. Each `@tool` function is a thin wrapper around a concrete implementation in `src/tradingagents/dataflows/`.

### 2.1 Architecture Overview

```
Tool Function (@tool)  -->  y_finance / yfinance_news backend  -->  yfinance
```

Tool definitions under `agents/utils/*_tools.py` import their backend function directly — there is no routing or vendor indirection layer.

### 2.2 Core Files

| File                            | Purpose                                                                                                   |
| ------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `dataflows/y_finance.py`        | Stock price, fundamentals, insider transactions, and windowed indicator calculation                       |
| `dataflows/yfinance_news.py`    | Ticker-specific news and global macro news                                                                |
| `dataflows/stockstats_utils.py` | `StockstatsUtils.get_stock_stats()` single-value indicator lookup used as fallback by `y_finance`         |
| `dataflows/interface.py`        | Re-exports backend functions for external consumers (does not alter behavior)                             |
| `dataflows/config.py`           | Global config container via `set_config` / `get_config`; used by cache lookups to locate `data_cache_dir` |

### 2.3 Tool-to-Backend Mapping

| Tool                       | Backend Function                              |
| -------------------------- | --------------------------------------------- |
| `get_stock_data`           | `y_finance.get_yfin_data_online`              |
| `get_indicators`           | `y_finance.get_stock_stats_indicators_window` |
| `get_fundamentals`         | `y_finance.get_fundamentals`                  |
| `get_balance_sheet`        | `y_finance.get_balance_sheet`                 |
| `get_cashflow`             | `y_finance.get_cashflow`                      |
| `get_income_statement`     | `y_finance.get_income_statement`              |
| `get_news`                 | `yfinance_news.get_news_yfinance`             |
| `get_global_news`          | `yfinance_news.get_global_news_yfinance`      |
| `get_insider_transactions` | `y_finance.get_insider_transactions`          |

### 2.4 Caching

`_get_stock_stats_bulk()` (in `y_finance.py`) downloads **15 years** of daily OHLCV data per symbol and persists it as CSV under `config.data_cache_dir` (default: `dataflows/data_cache/`). Subsequent `get_indicators` calls for the same symbol reuse the cached file and compute the indicator over the cached dataframe with `stockstats.wrap`. `StockstatsUtils.get_stock_stats` uses an identical caching strategy, only for a single-date lookup.

---

## 3. Complete Agent List and Detailed Definitions

### 3.1 Agent Role Categories

The system contains **12** agent roles plus **2** supporting components:

| Category        | Agent                               | Uses Tools                                                                      | LLM Tier |
| --------------- | ----------------------------------- | ------------------------------------------------------------------------------- | -------- |
| **Analyst**     | Market Analyst                      | `get_stock_data`, `get_indicators`                                              | quick    |
| **Analyst**     | Social Media Analyst                | `get_news`                                                                      | quick    |
| **Analyst**     | News Analyst                        | `get_news`, `get_global_news`                                                   | quick    |
| **Analyst**     | Fundamentals Analyst                | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | quick    |
| **Researcher**  | Bull Researcher                     | None                                                                            | quick    |
| **Researcher**  | Bear Researcher                     | None                                                                            | quick    |
| **Manager**     | Research Manager (investment judge) | None                                                                            | deep     |
| **Trader**      | Trader                              | None                                                                            | quick    |
| **Risk Debate** | Aggressive Debator                  | None                                                                            | quick    |
| **Risk Debate** | Conservative Debator                | None                                                                            | quick    |
| **Risk Debate** | Neutral Debator                     | None                                                                            | quick    |
| **Manager**     | Risk Manager (risk judge)           | None                                                                            | deep     |
| *Support*       | *Reflector*                         | *None*                                                                          | *quick*  |
| *Support*       | *SignalProcessor*                   | *None*                                                                          | *quick*  |

### 3.2 Detailed Definition of Each Agent

#### Market Analyst - Market technical analyst

| Item                     | Content                                                                                                                                                                                                                                              |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**      | `agents/analysts/market_analyst.py`                                                                                                                                                                                                                  |
| **Factory Function**     | `create_market_analyst(llm: BaseChatModel)`                                                                                                                                                                                                          |
| **LLM**                  | `quick_thinking_llm` + `bind_tools([get_stock_data, get_indicators])`                                                                                                                                                                                |
| **Prompt Location**      | `agents/prompts/market_analyst.md`                                                                                                                                                                                                                   |
| **Responsibilities**     | Select up to 8 complementary technical indicators for the target market regime. The prompt enforces calling `get_stock_data` before `get_indicators`, and the analyst must emit a detailed report that ends with a Markdown summary table.           |
| **Available Indicators** | `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma` (as listed in `market_analyst.md`; `y_finance.py` also accepts `mfi` but it is intentionally excluded from the prompt) |
| **Output**               | Writes the final report into `state.market_report`                                                                                                                                                                                                   |

#### Social Media Analyst - Social sentiment analyst

| Item                 | Content                                                                                                                                   |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `agents/analysts/social_media_analyst.py`                                                                                                 |
| **Factory Function** | `create_social_media_analyst(llm: BaseChatModel)`                                                                                         |
| **LLM**              | `quick_thinking_llm` + `bind_tools([get_news])`                                                                                           |
| **Prompt Location**  | `agents/prompts/social_media_analyst.md`                                                                                                  |
| **Responsibilities** | Analyze the sentiment trend in company-related news / social coverage and produce a report with sentiment assessment and Markdown tables. |
| **Output**           | Writes the final report into `state.sentiment_report`                                                                                     |

#### News Analyst - News analyst

| Item                 | Content                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Definition File**  | `agents/analysts/news_analyst.py`                                                                            |
| **Factory Function** | `create_news_analyst(llm: BaseChatModel)`                                                                    |
| **LLM**              | `quick_thinking_llm` + `bind_tools([get_news, get_global_news])`                                             |
| **Prompt Location**  | `agents/prompts/news_analyst.md`                                                                             |
| **Responsibilities** | Analyze company news and global macro news, and produce a trading-oriented news report with Markdown tables. |
| **Output**           | Writes the final report into `state.news_report`                                                             |

#### Fundamentals Analyst - Fundamentals analyst

| Item                 | Content                                                                                                                                   |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `agents/analysts/fundamentals_analyst.py`                                                                                                 |
| **Factory Function** | `create_fundamentals_analyst(llm: BaseChatModel)`                                                                                         |
| **LLM**              | `quick_thinking_llm` + `bind_tools([get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement])`                            |
| **Prompt Location**  | `agents/prompts/fundamentals_analyst.md`                                                                                                  |
| **Responsibilities** | Analyze fundamentals overview, balance sheets, cash flows, and income statements, and produce a fundamentals report with Markdown tables. |
| **Output**           | Writes the final report into `state.fundamentals_report`                                                                                  |

#### Bull Researcher - Bullish researcher

| Item                 | Content                                                                                                                                                               |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `agents/researchers/bull_researcher.py`                                                                                                                               |
| **Factory Function** | `create_bull_researcher(llm: BaseChatModel, memory: FinancialSituationMemory)`                                                                                        |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                                                                                                |
| **Prompt Location**  | `agents/prompts/bull_researcher.md`                                                                                                                                   |
| **Input**            | `market_report`, `sentiment_report`, `news_report`, `fundamentals_report`, cumulative debate history, latest bear response, and top-k past memories retrieved by BM25 |
| **Responsibilities** | Present bullish arguments focused on growth potential, competitive strengths, and positive catalysts, while rebutting the bear view.                                  |
| **Output**           | Appends `"Bull Analyst: ..."` into `investment_debate_state.{history,bull_history,current_response}` and increments `count`                                           |

#### Bear Researcher - Bearish researcher

| Item                 | Content                                                                                                                     |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `agents/researchers/bear_researcher.py`                                                                                     |
| **Factory Function** | `create_bear_researcher(llm: BaseChatModel, memory: FinancialSituationMemory)`                                              |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                                                      |
| **Prompt Location**  | `agents/prompts/bear_researcher.md`                                                                                         |
| **Input**            | Same as Bull Researcher, but receives the latest bull response                                                              |
| **Responsibilities** | Present bearish arguments focused on risks, competitive weaknesses, and negative catalysts, while rebutting the bull view.  |
| **Output**           | Appends `"Bear Analyst: ..."` into `investment_debate_state.{history,bear_history,current_response}` and increments `count` |

#### Research Manager - Investment judge

| Item                 | Content                                                                                                   |
| -------------------- | --------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `agents/managers/research_manager.py`                                                                     |
| **Factory Function** | `create_research_manager(llm: BaseChatModel, memory: FinancialSituationMemory)`                           |
| **LLM**              | `deep_thinking_llm` (no tool binding)                                                                     |
| **Prompt Location**  | `agents/prompts/research_manager.md`                                                                      |
| **Input**            | Full Bull/Bear debate transcript plus top-k past `invest_judge_memory`                                    |
| **Responsibilities** | Evaluate the Bull/Bear debate, decide Buy/Sell/Hold, and produce an investment plan.                      |
| **Output**           | Writes `state.investment_plan` and populates `investment_debate_state.{judge_decision, current_response}` |

#### Trader - Trader

| Item                 | Content                                                                                                                                   |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `agents/trader/trader.py`                                                                                                                 |
| **Factory Function** | `create_trader(llm: BaseChatModel, memory: FinancialSituationMemory)` (returned via `functools.partial(..., name="Trader")`)              |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                                                                    |
| **Prompt Location**  | `agents/prompts/trader_system.md` (system) + `agents/prompts/trader_user.md` (user)                                                       |
| **Input**            | `investment_plan`, `company_of_interest`, and top-k past `trader_memory`                                                                  |
| **Responsibilities** | Build a concrete trading plan based on the investment plan. The output **must** end with `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`. |
| **Output**           | Writes `state.trader_investment_plan` and sets `state.sender = "Trader"`                                                                  |

#### Aggressive Debator - Aggressive risk debator

| Item                 | Content                                                                                                                                                                             |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `agents/risk_mgmt/aggressive_debator.py`                                                                                                                                            |
| **Factory Function** | `create_aggressive_debator(llm: BaseChatModel)`                                                                                                                                     |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                                                                                                              |
| **Prompt Location**  | `agents/prompts/aggressive_debator.md`                                                                                                                                              |
| **Input**            | `trader_investment_plan`, the four analyst reports, full `risk_debate_state.history`, and the latest Conservative/Neutral responses                                                 |
| **Responsibilities** | Argue from a high-risk, high-reward perspective, emphasizing upside potential, growth, and innovation opportunities.                                                                |
| **Output**           | Appends `"Aggressive Analyst: ..."` into `risk_debate_state.{history, aggressive_history, current_aggressive_response}`, sets `latest_speaker="Aggressive"`, and increments `count` |

#### Conservative Debator - Conservative risk debator

| Item                 | Content                                                                                                                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `agents/risk_mgmt/conservative_debator.py`                                                                                                                                                  |
| **Factory Function** | `create_conservative_debator(llm: BaseChatModel)`                                                                                                                                           |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                                                                                                                      |
| **Prompt Location**  | `agents/prompts/conservative_debator.md`                                                                                                                                                    |
| **Input**            | Same as Aggressive Debator, but receives the latest Aggressive/Neutral responses                                                                                                            |
| **Responsibilities** | Argue from an asset-protection perspective, emphasizing lower volatility and stable growth.                                                                                                 |
| **Output**           | Appends `"Conservative Analyst: ..."` into `risk_debate_state.{history, conservative_history, current_conservative_response}`, sets `latest_speaker="Conservative"`, and increments `count` |

#### Neutral Debator - Neutral risk debator

| Item                 | Content                                                                                                                                                                 |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `agents/risk_mgmt/neutral_debator.py`                                                                                                                                   |
| **Factory Function** | `create_neutral_debator(llm: BaseChatModel)`                                                                                                                            |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                                                                                                  |
| **Prompt Location**  | `agents/prompts/neutral_debator.md`                                                                                                                                     |
| **Input**            | Same as Aggressive Debator, but receives the latest Aggressive/Conservative responses                                                                                   |
| **Responsibilities** | Balance risk and return while challenging both aggressive and conservative viewpoints.                                                                                  |
| **Output**           | Appends `"Neutral Analyst: ..."` into `risk_debate_state.{history, neutral_history, current_neutral_response}`, sets `latest_speaker="Neutral"`, and increments `count` |

#### Risk Manager - Risk judge

| Item                 | Content                                                                                                        |
| -------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `agents/managers/risk_manager.py`                                                                              |
| **Factory Function** | `create_risk_manager(llm: BaseChatModel, memory: FinancialSituationMemory)`                                    |
| **LLM**              | `deep_thinking_llm` (no tool binding)                                                                          |
| **Prompt Location**  | `agents/prompts/risk_manager.md`                                                                               |
| **Input**            | Full risk debate history, `investment_plan`, and top-k past `risk_manager_memory`                              |
| **Responsibilities** | Evaluate the three-way risk debate, revise the trader's plan, and produce the final Buy/Sell/Hold decision.    |
| **Output**           | Writes `state.final_trade_decision` and populates `risk_debate_state.{judge_decision, latest_speaker="Judge"}` |

### 3.3 Prompt Management

All agent prompts are stored as Markdown templates under `agents/prompts/`. The helper `load_prompt(name)` (`agents/prompts/__init__.py`) reads `prompts/{name}.md` and returns the raw text. Callers then either:

- fill the placeholders directly via `str.format(**kwargs)` (used by researchers, managers, trader, and risk debators), **or**
- pass the string to `ChatPromptTemplate.from_messages([...])` and fill the placeholders via `prompt.partial(...)` (used by all four analysts).

| Prompt File               | Agent                | Placeholders                                                                                                                                                                                     |
| ------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `market_analyst.md`       | Market Analyst       | `{tool_names}`, `{current_date}`, `{ticker}`                                                                                                                                                     |
| `news_analyst.md`         | News Analyst         | `{tool_names}`, `{current_date}`, `{ticker}`                                                                                                                                                     |
| `social_media_analyst.md` | Social Media Analyst | `{tool_names}`, `{current_date}`, `{ticker}`                                                                                                                                                     |
| `fundamentals_analyst.md` | Fundamentals Analyst | `{tool_names}`, `{current_date}`, `{ticker}`                                                                                                                                                     |
| `bull_researcher.md`      | Bull Researcher      | `{market_research_report}`, `{sentiment_report}`, `{news_report}`, `{fundamentals_report}`, `{history}`, `{current_response}`, `{past_memory_str}`                                               |
| `bear_researcher.md`      | Bear Researcher      | same as Bull Researcher                                                                                                                                                                          |
| `research_manager.md`     | Research Manager     | `{past_memory_str}`, `{history}`                                                                                                                                                                 |
| `trader_system.md`        | Trader (system)      | `{past_memory_str}`                                                                                                                                                                              |
| `trader_user.md`          | Trader (user)        | `{company_name}`, `{investment_plan}`                                                                                                                                                            |
| `aggressive_debator.md`   | Aggressive Debator   | `{trader_decision}`, `{market_research_report}`, `{sentiment_report}`, `{news_report}`, `{fundamentals_report}`, `{history}`, `{current_conservative_response}`, `{current_neutral_response}`    |
| `conservative_debator.md` | Conservative Debator | `{trader_decision}`, `{market_research_report}`, `{sentiment_report}`, `{news_report}`, `{fundamentals_report}`, `{history}`, `{current_aggressive_response}`, `{current_neutral_response}`      |
| `neutral_debator.md`      | Neutral Debator      | `{trader_decision}`, `{market_research_report}`, `{sentiment_report}`, `{news_report}`, `{fundamentals_report}`, `{history}`, `{current_aggressive_response}`, `{current_conservative_response}` |
| `risk_manager.md`         | Risk Manager         | `{trader_plan}`, `{past_memory_str}`, `{history}`                                                                                                                                                |
| `reflector.md`            | Reflector            | (no placeholders; loaded as the system message inside `Reflector._reflect_on_component`)                                                                                                         |

### 3.4 Other Notes

- Only the 4 **analysts** use tools (Function Calling); every other agent relies purely on LLM reasoning over state text.
- **Bull / Bear / Trader / Research Manager / Risk Manager** retrieve BM25 past experiences from `FinancialSituationMemory`.
- **Aggressive / Conservative / Neutral Debator** do **not** use memory.
- After each analyst block the graph inserts a `Msg Clear {Analyst}` node that emits `RemoveMessage` entries for the entire `messages` history and appends a `HumanMessage("Continue")` placeholder so the next analyst starts fresh while remaining compatible with Anthropic's message format requirements.

---

## 4. Complete LangGraph Workflow

### 4.1 Core Files

All six classes below are Pydantic `BaseModel` subclasses.

| File                                           | Purpose                                                                                                                                                 |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/tradingagents/graph/trading_graph.py`     | `TradingAgentsGraph` — main orchestrator; initializes LLMs, memories, and `ToolNode`s via `@computed_field`/`@cached_property`, then compiles the graph |
| `src/tradingagents/graph/setup.py`             | `MemoryComponents` — groups the 5 memory instances; `GraphSetup` — registers nodes/edges and compiles the `StateGraph`                                  |
| `src/tradingagents/graph/conditional_logic.py` | `ConditionalLogic` — conditional routing logic for analyst loops and debate loops                                                                       |
| `src/tradingagents/graph/propagation.py`       | `Propagator` — builds the initial graph state and supplies LangGraph invocation arguments                                                               |
| `src/tradingagents/graph/reflection.py`        | `Reflector` — performs post-trade reflection and updates the five memories                                                                              |
| `src/tradingagents/graph/signal_processing.py` | `SignalProcessor` — extracts BUY/SELL/HOLD from the Risk Judge's natural-language output                                                                |

### 4.2 Graph Node List

Nodes registered in `GraphSetup.setup_graph()`:

| Node Name                | Handler                                                                               | Description                         |
| ------------------------ | ------------------------------------------------------------------------------------- | ----------------------------------- |
| `Market Analyst`         | `create_market_analyst(quick_thinking_llm)`                                           | Market analysis                     |
| `tools_market`           | `ToolNode([get_stock_data, get_indicators])`                                          | Market tool execution               |
| `Msg Clear Market`       | `create_msg_delete()`                                                                 | Clear conversation history          |
| `Social Analyst`         | `create_social_media_analyst(quick_thinking_llm)`                                     | Social analysis                     |
| `tools_social`           | `ToolNode([get_news])`                                                                | Social tool execution               |
| `Msg Clear Social`       | `create_msg_delete()`                                                                 | Clear conversation history          |
| `News Analyst`           | `create_news_analyst(quick_thinking_llm)`                                             | News analysis                       |
| `tools_news`             | `ToolNode([get_news, get_global_news, get_insider_transactions])`                     | News tool execution (see note §1.4) |
| `Msg Clear News`         | `create_msg_delete()`                                                                 | Clear conversation history          |
| `Fundamentals Analyst`   | `create_fundamentals_analyst(quick_thinking_llm)`                                     | Fundamentals analysis               |
| `tools_fundamentals`     | `ToolNode([get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement])` | Fundamentals tool execution         |
| `Msg Clear Fundamentals` | `create_msg_delete()`                                                                 | Clear conversation history          |
| `Bull Researcher`        | `create_bull_researcher(quick_thinking_llm, bull_memory)`                             | Bullish debate                      |
| `Bear Researcher`        | `create_bear_researcher(quick_thinking_llm, bear_memory)`                             | Bearish debate                      |
| `Research Manager`       | `create_research_manager(deep_thinking_llm, invest_judge_memory)`                     | Investment judge                    |
| `Trader`                 | `create_trader(quick_thinking_llm, trader_memory)`                                    | Trading decision                    |
| `Aggressive Analyst`     | `create_aggressive_debator(quick_thinking_llm)`                                       | Aggressive risk analysis            |
| `Neutral Analyst`        | `create_neutral_debator(quick_thinking_llm)`                                          | Neutral risk analysis               |
| `Conservative Analyst`   | `create_conservative_debator(quick_thinking_llm)`                                     | Conservative risk analysis          |
| `Risk Judge`             | `create_risk_manager(deep_thinking_llm, risk_manager_memory)`                         | Final risk judge                    |

The analyst / tool / Msg Clear triplet is registered via a loop over `selected_analysts` in `GraphSetup.setup_graph()`, so any subset of analysts (or a reordered list) is supported. The rest of the graph is fixed.

### 4.3 Edge Definitions

#### Fixed Edges (Unconditional)

| From                  | To                                                           | Where it is added               |
| --------------------- | ------------------------------------------------------------ | ------------------------------- |
| `START`               | First analyst (default: `Market Analyst`)                    | `GraphSetup.setup_graph`        |
| `tools_{analyst}`     | `{Analyst} Analyst` (return to the same analyst to continue) | `GraphSetup._add_analyst_edges` |
| `Msg Clear {Analyst}` | Next analyst, or `Bull Researcher` if it is the last one     | `GraphSetup._add_analyst_edges` |
| `Research Manager`    | `Trader`                                                     | `GraphSetup.setup_graph`        |
| `Trader`              | `Aggressive Analyst`                                         | `GraphSetup.setup_graph`        |
| `Risk Judge`          | `END`                                                        | `GraphSetup.setup_graph`        |

#### Conditional Edges - Defined in `ConditionalLogic`

**Analyst tool loop** (`should_continue_market` / `_social` / `_news` / `_fundamentals`):

```
{Analyst} --> should_continue_{type}() --> tools_{type}       (if the last message has tool_calls)
                                       `--> Msg Clear {Type}  (if there are no tool_calls, analysis is complete)
```

**Investment debate loop** (`should_continue_debate`):

```
Bull Researcher --> should_continue_debate() --> Bear Researcher    (after Bull speaks)
                                              `--> Research Manager (when count >= 2 * max_debate_rounds)

Bear Researcher --> should_continue_debate() --> Bull Researcher    (after Bear speaks)
                                              `--> Research Manager (when count >= 2 * max_debate_rounds)
```

- Termination condition: `count >= 2 * max_debate_rounds` (default `max_debate_rounds = 1`, so one round from each side).
- Routing key: whether `current_response` starts with `"Bull"`.

**Risk debate loop** (`should_continue_risk_analysis`):

```
Aggressive   --> should_continue_risk_analysis() --> Conservative Analyst  (after Aggressive speaks)
                                                  `--> Risk Judge           (when count >= 3 * max_risk_discuss_rounds)

Conservative --> should_continue_risk_analysis() --> Neutral Analyst       (after Conservative speaks)
                                                  `--> Risk Judge           (when count >= 3 * max_risk_discuss_rounds)

Neutral      --> should_continue_risk_analysis() --> Aggressive Analyst    (after Neutral speaks)
                                                  `--> Risk Judge           (when count >= 3 * max_risk_discuss_rounds)
```

- Termination condition: `count >= 3 * max_risk_discuss_rounds` (default `max_risk_discuss_rounds = 1`, so one round per stance).
- Routing key: `risk_debate_state.latest_speaker`.
- Rotation order: **Aggressive → Conservative → Neutral → Aggressive → …**

### 4.4 Full Flow Diagram

```
START
  |
  v
+-------------------- Phase 1: Data Collection and Analysis --------------------+
|                                                                                |
|  Market Analyst <--> tools_market (loop until there are no more tool_calls)   |
|       |                                                                        |
|       v                                                                        |
|  Msg Clear Market                                                              |
|       |                                                                        |
|       v                                                                        |
|  Social Analyst <--> tools_social                                              |
|       |                                                                        |
|       v                                                                        |
|  Msg Clear Social                                                              |
|       |                                                                        |
|       v                                                                        |
|  News Analyst <--> tools_news                                                  |
|       |                                                                        |
|       v                                                                        |
|  Msg Clear News                                                                |
|       |                                                                        |
|       v                                                                        |
|  Fundamentals Analyst <--> tools_fundamentals                                  |
|       |                                                                        |
|       v                                                                        |
|  Msg Clear Fundamentals                                                        |
|                                                                                |
+--------------------------------------------------------------------------------+
        |
        v
+-------------------- Phase 2: Investment Research Debate -----------------------+
|                                                                                |
|  Bull Researcher <--------- debate loop ---------> Bear Researcher             |
|                     (for max_debate_rounds rounds)                             |
|                           |                                                    |
|                           v                                                    |
|                    Research Manager                                            |
|                 (produces investment plan)                                     |
|                                                                                |
+--------------------------------------------------------------------------------+
        |
        v
+-------------------- Phase 3: Trading Decision --------------------------------+
|                                                                                |
|                           Trader                                               |
|                   (creates trading plan)                                       |
|                                                                                |
+--------------------------------------------------------------------------------+
        |
        v
+-------------------- Phase 4: Risk Control Debate ------------------------------+
|                                                                                |
|  Aggressive --> Conservative --> Neutral --> (loop)                            |
|                (for max_risk_discuss_rounds rounds)                            |
|                           |                                                    |
|                           v                                                    |
|                       Risk Judge                                               |
|                   (final trading decision)                                     |
|                                                                                |
+--------------------------------------------------------------------------------+
        |
        v
       END
```

### 4.5 Graph Compilation and Execution Entry Points

- **Main class:** `TradingAgentsGraph` (`graph/trading_graph.py`) — Pydantic `BaseModel` subclass. User-configurable fields use `Field()`; derived state (LLMs, memories, `tool_nodes`, compiled graph, propagator, reflector, signal_processor) is exposed via `@computed_field` + `@cached_property`.
- **Full Pydantic coverage:** Every class in `src/tradingagents/graph/` — `TradingAgentsGraph`, `GraphSetup`, `MemoryComponents`, `ConditionalLogic`, `Propagator`, `Reflector`, and `SignalProcessor` — inherits from `BaseModel`. Non-Pydantic dependencies (LangChain `BaseChatModel`, LangGraph `ToolNode`, `FinancialSituationMemory`) are wrapped with `ConfigDict(arbitrary_types_allowed=True)`.
- **Configuration:** Accepts a `TradingAgentsConfig` Pydantic model. Side effects (`set_config`, `data_cache_dir.mkdir(...)`) run in a `@model_validator(mode="after")` hook named `_setup`.
- **Execution:** `propagate(company_name, trade_date) -> (AgentState, str)` builds the initial state via `Propagator.create_initial_state`, calls either `graph.stream()` (if `debug=True`) or `graph.invoke()`, logs the final state to `eval_results/{ticker}/TradingAgentsStrategy_logs/full_states_log_{trade_date}.json`, then invokes `process_signal()` on the final decision and returns both the state and the extracted signal.
- **Reflection:** `reflect_and_remember(returns_losses)` — runs all five `Reflector.reflect_*` methods against the cached `curr_state`.
- **Signal extraction:** `process_signal(full_signal)` — delegates to `SignalProcessor.process_signal`.

---

## 5. Shared State Structure (State Schema)

Defined in `src/tradingagents/agents/utils/agent_states.py`. All three classes are **Pydantic `BaseModel`** subclasses — **not** LangGraph's `MessagesState`. The conversational history is modeled as a regular Pydantic field annotated with LangGraph's `add_messages` reducer.

### `AgentState` - Main state shared across all nodes

| Field                     | Type                                        | Description                                                | Written By                                       |
| ------------------------- | ------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------ |
| `messages`                | `Annotated[list[AnyMessage], add_messages]` | Conversation history reduced by LangGraph's `add_messages` | All agents (plus `Msg Clear *` nodes)            |
| `company_of_interest`     | `str`                                       | Company / ticker being traded                              | Initialization (`Propagator`)                    |
| `trade_date`              | `str`                                       | Trading date                                               | Initialization (`Propagator`)                    |
| `sender`                  | `str`                                       | Name of the agent that most recently wrote to the state    | All agents                                       |
| `market_report`           | `str`                                       | Market analysis report                                     | Market Analyst                                   |
| `sentiment_report`        | `str`                                       | Social sentiment report                                    | Social Media Analyst                             |
| `news_report`             | `str`                                       | News analysis report                                       | News Analyst                                     |
| `fundamentals_report`     | `str`                                       | Fundamentals report                                        | Fundamentals Analyst                             |
| `investment_debate_state` | `InvestDebateState`                         | Bull/Bear debate state                                     | Bull / Bear / Research Manager                   |
| `investment_plan`         | `str`                                       | Investment plan                                            | Research Manager                                 |
| `trader_investment_plan`  | `str`                                       | Trading plan                                               | Trader                                           |
| `risk_debate_state`       | `RiskDebateState`                           | Risk debate state                                          | Aggressive / Conservative / Neutral / Risk Judge |
| `final_trade_decision`    | `str`                                       | Final trading decision                                     | Risk Judge                                       |

The class is decorated with `ConfigDict(arbitrary_types_allowed=True)` so that the `messages` field — whose element type is `AnyMessage` from LangChain — validates cleanly under Pydantic v2.

### `InvestDebateState`

| Field              | Type  | Description                                     |
| ------------------ | ----- | ----------------------------------------------- |
| `bull_history`     | `str` | Cumulative debate transcript from the bull side |
| `bear_history`     | `str` | Cumulative debate transcript from the bear side |
| `history`          | `str` | Combined debate transcript                      |
| `current_response` | `str` | Most recent response (used for routing)         |
| `judge_decision`   | `str` | Final decision made by the Research Manager     |
| `count`            | `int` | Number of debate turns completed                |

### `RiskDebateState`

| Field                           | Type  | Description                                         |
| ------------------------------- | ----- | --------------------------------------------------- |
| `aggressive_history`            | `str` | Cumulative transcript from the aggressive debator   |
| `conservative_history`          | `str` | Cumulative transcript from the conservative debator |
| `neutral_history`               | `str` | Cumulative transcript from the neutral debator      |
| `history`                       | `str` | Combined risk debate transcript                     |
| `latest_speaker`                | `str` | Most recent speaker (used for routing)              |
| `current_aggressive_response`   | `str` | Latest aggressive response                          |
| `current_conservative_response` | `str` | Latest conservative response                        |
| `current_neutral_response`      | `str` | Latest neutral response                             |
| `judge_decision`                | `str` | Final decision made by the Risk Manager             |
| `count`                         | `int` | Number of debate turns completed                    |

---

## 6. Supporting Components (Memory / Reflection / Signal Processing)

### 6.1 FinancialSituationMemory - Memory system

- **File:** `agents/utils/memory.py`
- **Algorithm:** `BM25Okapi` (lexical BM25 similarity, no external API required)
- **Storage:** Plain Python lists of `(situation, recommendation)` pairs, rebuilt into a BM25 index on every `add_situations` call
- **Retrieval:** `get_memories(current_situation, n_matches)` tokenizes the query, computes BM25 scores, and returns the top-`n` documents with normalized similarity scores. Returns `[]` when the index is empty.
- **Instances:** 5 per trading run — `bull_memory`, `bear_memory`, `trader_memory`, `invest_judge_memory`, `risk_manager_memory`. Created as `@cached_property`s on `TradingAgentsGraph`.

### 6.2 Reflector - Reflection system

- **File:** `graph/reflection.py`
- **Class:** `Reflector` — Pydantic `BaseModel` with `ConfigDict(arbitrary_types_allowed=True)`
- **Field:** `quick_thinking_llm: BaseChatModel` — LLM used to generate the reflection analysis
- **System prompt:** Loaded from `agents/prompts/reflector.md` via `load_prompt("reflector")` inside `_reflect_on_component`. The user-side message is synthesized from `returns_losses`, the component's output, and the concatenated `situation` text built from the four analyst reports.
- **Purpose:** After the trade outcome is known, reflect on each agent's decision quality based on the actual profit/loss and store the reflection into the corresponding BM25 memory so it can influence future runs.
- **Trigger:** `TradingAgentsGraph.reflect_and_remember(returns_losses)` runs reflection in this order:
    1. `reflect_bull_researcher()` — writes into `bull_memory`
    2. `reflect_bear_researcher()` — writes into `bear_memory`
    3. `reflect_trader()` — writes into `trader_memory`
    4. `reflect_invest_judge()` — writes into `invest_judge_memory`
    5. `reflect_risk_manager()` — writes into `risk_manager_memory`

### 6.3 SignalProcessor - Signal extraction

- **File:** `graph/signal_processing.py`
- **Class:** `SignalProcessor` — Pydantic `BaseModel` with `ConfigDict(arbitrary_types_allowed=True)`
- **Field:** `quick_thinking_llm: BaseChatModel` — LLM used to extract the decision (typed against LangChain's abstract `BaseChatModel` so any provider client works).
- **Prompt:** Inline, constructed inside `process_signal` — a short system message asking the model to return only `SELL`, `BUY`, or `HOLD`.
- **Purpose:** Extracts `BUY` / `SELL` / `HOLD` from the Risk Judge's natural-language output. Called automatically at the end of `TradingAgentsGraph.propagate`.

---

## 7. LLM Configuration

### 7.1 Configuration Locations

- **Config model:** `src/tradingagents/default_config.py`
    - `LLMProvider` — `StrEnum` of the 6 supported providers
    - `ReasoningEffort` — `StrEnum` of `low` / `medium` / `high` / `max`, mapped per-provider at the client layer
    - `TradingAgentsConfig` — Pydantic `BaseModel` that carries directories, LLM provider/model names, debate caps, and the recursion limit
- **LLM factory:** `src/tradingagents/llm_clients/factory.py` — `create_llm_client(provider, model, **kwargs)`
- **Client classes:**
    - `llm_clients/openai_client.py` — `OpenAIClient` and `UnifiedChatOpenAI`; strips `temperature` / `top_p` for reasoning models (o1, o3, gpt-5\*) and hardcodes the per-provider `base_url` plus API-key routing for OpenAI / xAI / OpenRouter / Ollama
    - `llm_clients/anthropic_client.py` — `AnthropicClient`
    - `llm_clients/google_client.py` — `GoogleClient` and `NormalizedChatGoogleGenerativeAI`; flattens Gemini 3's list-of-parts content into a plain string and maps `ReasoningEffort` to either Gemini 3 `thinking_level` or Gemini 2.5 `thinking_budget`

### 7.2 LLM Tier Assignment

`TradingAgentsConfig.quick_think_llm` and `TradingAgentsConfig.deep_think_llm` are **required** fields — there is no built-in default. The user must specify a model name for each tier when constructing `TradingAgentsConfig`.

| Variable             | Config Key        | Usage                                                                        |
| -------------------- | ----------------- | ---------------------------------------------------------------------------- |
| `quick_thinking_llm` | `quick_think_llm` | All analysts, researchers, trader, debators, reflector, and signal processor |
| `deep_thinking_llm`  | `deep_think_llm`  | Research Manager and Risk Manager                                            |

Both LLM instances are created lazily through `TradingAgentsGraph._create_llm`, which calls `create_llm_client(...)` with the configured provider, model, optional `reasoning_effort`, and the optional callbacks list. The endpoint URL is no longer configurable — each provider's `base_url` is hardcoded inside `OpenAIClient`.

### 7.3 Supported LLM Providers

| Provider   | `LLMProvider` enum value | Client Class                    | Notes                                                                            |
| ---------- | ------------------------ | ------------------------------- | -------------------------------------------------------------------------------- |
| OpenAI     | `openai`                 | `OpenAIClient`                  | Default; strips reasoning-incompatible args for o1/o3/gpt-5 models               |
| Anthropic  | `anthropic`              | `AnthropicClient`               | Uses LangChain's `ChatAnthropic`                                                 |
| Google     | `google`                 | `GoogleClient`                  | Normalizes Gemini 3 content; maps reasoning effort per model                     |
| xAI        | `xai`                    | `OpenAIClient` (API-compatible) | Auto-sets `base_url=https://api.x.ai/v1` and reads `XAI_API_KEY`                 |
| Ollama     | `ollama`                 | `OpenAIClient` (API-compatible) | Auto-sets `base_url=http://localhost:11434/v1`                                   |
| OpenRouter | `openrouter`             | `OpenAIClient` (API-compatible) | Auto-sets `base_url=https://openrouter.ai/api/v1` and reads `OPENROUTER_API_KEY` |

---

## 8. Key Dependency List (To Be Removed)

The following LangGraph/LangChain dependencies will need to be replaced or removed during the planned refactor:

| Dependency               | Purpose                                                                                                 | Impact Scope                                                                        |
| ------------------------ | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `langgraph`              | Graph construction (`StateGraph`, `ToolNode`, `CompiledStateGraph`, `add_messages`)                     | `graph/setup.py`, `graph/trading_graph.py`, `agent_states.py`                       |
| `langchain_core`         | `BaseChatModel`, `@tool` decorator, `ChatPromptTemplate`, `HumanMessage`, `RemoveMessage`, `AnyMessage` | All agent definitions, `agent_states.py`, `agent_utils.py`, every `*_tools.py` file |
| `langchain_openai`       | `ChatOpenAI` (subclassed by `UnifiedChatOpenAI`)                                                        | `llm_clients/openai_client.py`                                                      |
| `langchain_anthropic`    | `ChatAnthropic`                                                                                         | `llm_clients/anthropic_client.py`                                                   |
| `langchain_google_genai` | `ChatGoogleGenerativeAI` (subclassed by `NormalizedChatGoogleGenerativeAI`)                             | `llm_clients/google_client.py`                                                      |

Core pieces that will need to be rebuilt during the refactor:

1. **Tool Calling mechanism** — replace the `@tool` decorator, `bind_tools`, and `ToolNode` trio with a first-party function-calling pipeline.
2. **Graph / workflow engine** — replace `StateGraph` nodes, unconditional edges, and conditional routing with a custom orchestrator that still preserves the Phase 1 → 4 flow documented above.
3. **State management** — replace `Annotated[list[AnyMessage], add_messages]` and LangGraph's reducer mechanics with an explicit, observable state container.
