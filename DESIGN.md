# System Architecture and Agent Inventory

This document records the TradingAgents system architecture, data acquisition methods, and the responsibilities and interaction flows of each agent. It serves as a reference for future refactoring and development of other agents.

> **Refactoring direction:** The long-term plan is to remove all LangGraph / LangChain related dependencies and replace them with a custom-built agent architecture. This document ensures that every existing feature and workflow has a complete reference during the refactor.

---

## Table of Contents

1. [Market Data and External Information Access (Tools / Function Calling)](#1-market-data-and-external-information-access-tools--function-calling)
2. [Data Routing Mechanism](#2-data-routing-mechanism)
3. [Complete Agent List and Detailed Definitions](#3-complete-agent-list-and-detailed-definitions)
4. [Complete LangGraph Workflow](#4-complete-langgraph-workflow)
5. [Shared State Structure (State Schema)](#5-shared-state-structure-state-schema)
6. [Supporting Components (Memory / Reflection / Signal Processing)](#6-supporting-components-memory--reflection--signal-processing)
7. [LLM Configuration](#7-llm-configuration)
8. [Key Dependency List (To Be Removed)](#8-key-dependency-list-to-be-removed)

---

## 1. Market Data and External Information Access (Tools / Function Calling)

At present, market data, news, financial statements, and other information are provided to analyst agents through Function Calling tools defined with the **LangChain `@tool` decorator**. All tools are defined under `src/tradingagents/agents/utils/` and are re-exported centrally through `agent_utils.py`.

### 1.1 Tool Overview

There are **9** tools in total, grouped into 4 major categories:

| #   | Tool Name                  | Category             | Definition File                              | Line Range | Default Data Vendor |
| --- | -------------------------- | -------------------- | -------------------------------------------- | ---------- | ------------------- |
| 1   | `get_stock_data`           | core_stock_apis      | `agents/utils/core_stock_tools.py`           | 8-24       | yfinance            |
| 2   | `get_indicators`           | technical_indicators | `agents/utils/technical_indicators_tools.py` | 8-26       | yfinance            |
| 3   | `get_fundamentals`         | fundamental_data     | `agents/utils/fundamental_data_tools.py`     | 8-22       | yfinance            |
| 4   | `get_balance_sheet`        | fundamental_data     | `agents/utils/fundamental_data_tools.py`     | 25-41      | yfinance            |
| 5   | `get_cashflow`             | fundamental_data     | `agents/utils/fundamental_data_tools.py`     | 44-60      | yfinance            |
| 6   | `get_income_statement`     | fundamental_data     | `agents/utils/fundamental_data_tools.py`     | 63-79      | yfinance            |
| 7   | `get_news`                 | news_data            | `agents/utils/news_data_tools.py`            | 8-24       | yfinance            |
| 8   | `get_global_news`          | news_data            | `agents/utils/news_data_tools.py`            | 27-44      | yfinance            |
| 9   | `get_insider_transactions` | news_data            | `agents/utils/news_data_tools.py`            | 47-57      | yfinance            |

> All file paths are relative to `src/tradingagents/`

### 1.2 Detailed Parameters for Each Tool

#### `get_stock_data` - Stock OHLCV data

- **File:** `src/tradingagents/agents/utils/core_stock_tools.py` (L8-24)
- **Parameters:**
    - `symbol: str` - Stock ticker symbol (e.g. AAPL, TSM)
    - `start_date: str` - Start date (`yyyy-mm-dd`)
    - `end_date: str` - End date (`yyyy-mm-dd`)
- **Routing:** `route_to_vendor("get_stock_data", symbol, start_date, end_date)`

#### `get_indicators` - Technical analysis indicators

- **File:** `src/tradingagents/agents/utils/technical_indicators_tools.py` (L8-26)
- **Parameters:**
    - `symbol: str` - Stock ticker symbol
    - `indicator: str` - Technical indicator name
    - `curr_date: str` - Current trading date (`YYYY-mm-dd`)
    - `look_back_days: int = 30` - Look-back window in days
- **Routing:** `route_to_vendor("get_indicators", symbol, indicator, curr_date, look_back_days)`

#### `get_fundamentals` - Company fundamentals data

- **File:** `src/tradingagents/agents/utils/fundamental_data_tools.py` (L8-22)
- **Parameters:**
    - `ticker: str` - Stock ticker symbol
    - `curr_date: str` - Trading date (`yyyy-mm-dd`)
- **Routing:** `route_to_vendor("get_fundamentals", ticker, curr_date)`

#### `get_balance_sheet` - Balance sheet

- **File:** `src/tradingagents/agents/utils/fundamental_data_tools.py` (L25-41)
- **Parameters:**
    - `ticker: str` - Stock ticker symbol
    - `freq: str = "quarterly"` - Frequency (`annual` / `quarterly`)
    - `curr_date: str = None` - Trading date
- **Routing:** `route_to_vendor("get_balance_sheet", ticker, freq, curr_date)`

#### `get_cashflow` - Cash flow statement

- **File:** `src/tradingagents/agents/utils/fundamental_data_tools.py` (L44-60)
- **Parameters:** Same as `get_balance_sheet`
- **Routing:** `route_to_vendor("get_cashflow", ticker, freq, curr_date)`

#### `get_income_statement` - Income statement

- **File:** `src/tradingagents/agents/utils/fundamental_data_tools.py` (L63-79)
- **Parameters:** Same as `get_balance_sheet`
- **Routing:** `route_to_vendor("get_income_statement", ticker, freq, curr_date)`

#### `get_news` - Company-related news

- **File:** `src/tradingagents/agents/utils/news_data_tools.py` (L8-24)
- **Parameters:**
    - `ticker: str` - Stock ticker symbol
    - `start_date: str` - Start date (`yyyy-mm-dd`)
    - `end_date: str` - End date (`yyyy-mm-dd`)
- **Routing:** `route_to_vendor("get_news", ticker, start_date, end_date)`

#### `get_global_news` - Global macro news

- **File:** `src/tradingagents/agents/utils/news_data_tools.py` (L27-44)
- **Parameters:**
    - `curr_date: str` - Current date (`yyyy-mm-dd`)
    - `look_back_days: int = 7` - Look-back window in days
    - `limit: int = 5` - Maximum number of articles
- **Routing:** `route_to_vendor("get_global_news", curr_date, look_back_days, limit)`

#### `get_insider_transactions` - Insider transactions

- **File:** `src/tradingagents/agents/utils/news_data_tools.py` (L47-57)
- **Parameters:**
    - `ticker: str` - Stock ticker symbol
- **Routing:** `route_to_vendor("get_insider_transactions", ticker)`

### 1.3 Tool Export Entry Point

- **File:** `src/tradingagents/agents/utils/agent_utils.py` (L1-50)
- Re-exports all 9 tool functions from their respective tool modules in one place
- Also defines `create_msg_delete()` (L36-49), which creates a function for clearing conversation history when passing state between analysts

### 1.4 Tool-to-Analyst Binding

| Analyst              | Bound Tools                                                                     | ToolNode Name        |
| -------------------- | ------------------------------------------------------------------------------- | -------------------- |
| Market Analyst       | `get_stock_data`, `get_indicators`                                              | `tools_market`       |
| Social Media Analyst | `get_news`                                                                      | `tools_social`       |
| News Analyst         | `get_news`, `get_global_news`, `get_insider_transactions`                       | `tools_news`         |
| Fundamentals Analyst | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | `tools_fundamentals` |

Binding method:

- Each analyst creation function binds tools to the LLM through `llm.bind_tools(tools)`
- LangGraph `ToolNode` wrappers are created in `TradingAgentsGraph._create_tool_nodes()` (L146-172 of `graph/trading_graph.py`)

---

## 2. Data Routing Mechanism

All tool functions internally call `route_to_vendor()` for data routing, with support for automatic switching across multiple vendors.

### 2.1 Architecture Overview

```
Tool Function (@tool) --> route_to_vendor() --> Vendor Implementation
                              |
                              |-- get_category_for_method()  // Look up the tool category
                              |-- get_vendor()               // Fetch the vendor from config
                              `-- VENDOR_METHODS[method]     // Resolve the implementation function
```

### 2.2 Core Files

| File                     | Purpose                  | Key Contents                                                                           |
| ------------------------ | ------------------------ | -------------------------------------------------------------------------------------- |
| `dataflows/interface.py` | Routing core             | `TOOLS_CATEGORIES` (L25-39), `VENDOR_METHODS` (L44-79), `route_to_vendor()` (L109-137) |
| `dataflows/config.py`    | Configuration management | `initialize_config()` (L16-19), `set_config()` (L22-29), `get_config()` (L32-39)       |
| `default_config.py`      | Default settings         | `data_vendors` (L23-28), `tool_vendors` (L30-32)                                       |

### 2.3 Vendor Mapping Table

| Tool                       | yfinance Implementation                       | alpha_vantage Implementation             |
| -------------------------- | --------------------------------------------- | ---------------------------------------- |
| `get_stock_data`           | `y_finance.get_yfin_data_online`              | `alpha_vantage.get_stock`                |
| `get_indicators`           | `y_finance.get_stock_stats_indicators_window` | `alpha_vantage.get_indicator`            |
| `get_fundamentals`         | `y_finance.get_fundamentals`                  | `alpha_vantage.get_fundamentals`         |
| `get_balance_sheet`        | `y_finance.get_balance_sheet`                 | `alpha_vantage.get_balance_sheet`        |
| `get_cashflow`             | `y_finance.get_cashflow`                      | `alpha_vantage.get_cashflow`             |
| `get_income_statement`     | `y_finance.get_income_statement`              | `alpha_vantage.get_income_statement`     |
| `get_news`                 | `yfinance_news.get_news_yfinance`             | `alpha_vantage.get_news`                 |
| `get_global_news`          | `yfinance_news.get_global_news_yfinance`      | `alpha_vantage.get_global_news`          |
| `get_insider_transactions` | `y_finance.get_insider_transactions`          | `alpha_vantage.get_insider_transactions` |

### 2.4 Vendor Implementation Files

| File                                      | Purpose                                                                 |
| ----------------------------------------- | ----------------------------------------------------------------------- |
| `dataflows/y_finance.py`                  | yfinance stock price, fundamentals, and insider transaction data        |
| `dataflows/yfinance_news.py`              | yfinance news                                                           |
| `dataflows/stockstats_utils.py`           | Technical indicator calculations (used by `y_finance`)                  |
| `dataflows/alpha_vantage.py`              | Alpha Vantage main entry point                                          |
| `dataflows/alpha_vantage_stock.py`        | Alpha Vantage stock data                                                |
| `dataflows/alpha_vantage_news.py`         | Alpha Vantage news                                                      |
| `dataflows/alpha_vantage_fundamentals.py` | Alpha Vantage fundamentals                                              |
| `dataflows/alpha_vantage_indicator.py`    | Alpha Vantage technical indicators                                      |
| `dataflows/alpha_vantage_common.py`       | Alpha Vantage shared utilities (including `AlphaVantageRateLimitError`) |
| `dataflows/utils.py`                      | Shared utility functions                                                |

### 2.5 Fallback Mechanism

`route_to_vendor()` (`interface.py` L109-137) implements automatic fallback:

1. It first uses the configured primary vendor.
2. If an `AlphaVantageRateLimitError` occurs, it automatically switches to the next available vendor.
3. It supports comma-separated vendor lists in config as a fallback chain.

---

## 3. Complete Agent List and Detailed Definitions

### 3.1 Agent Role Categories

The system currently contains **12** agent roles plus **2** supporting components:

| Category        | Agent                               | Uses Tools                                                                      | LLM Tier |
| --------------- | ----------------------------------- | ------------------------------------------------------------------------------- | -------- |
| **Analyst**     | Market Analyst                      | `get_stock_data`, `get_indicators`                                              | quick    |
| **Analyst**     | Social Media Analyst                | `get_news`                                                                      | quick    |
| **Analyst**     | News Analyst                        | `get_news`, `get_global_news`, `get_insider_transactions`                       | quick    |
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

| Item                     | Content                                                                                                                                                                           |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**      | `src/tradingagents/agents/analysts/market_analyst.py`                                                                                                                             |
| **Factory Function**     | `create_market_analyst(llm: BaseChatModel)` (L10-73)                                                                                                                              |
| **LLM**                  | `quick_thinking_llm` + `bind_tools([get_stock_data, get_indicators])`                                                                                                             |
| **Prompt Location**      | `agents/prompts/market_analyst.md`                                                                                                                                                |
| **Responsibilities**     | Select up to 8 complementary technical indicators for analysis. It must call `get_stock_data` before `get_indicators`, and produce a detailed market report with Markdown tables. |
| **Available Indicators** | close_50_sma, close_200_sma, close_10_ema, macd, macds, macdh, rsi_14, boll, boll_ub, boll_lb, atr_14, vwma                                                                       |
| **Output**               | Writes to `state["market_report"]`                                                                                                                                                |

#### Social Media Analyst - Social sentiment analyst

| Item                 | Content                                                                                                                                   |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `src/tradingagents/agents/analysts/social_media_analyst.py`                                                                               |
| **Factory Function** | `create_social_media_analyst(llm: BaseChatModel)` (L10-52)                                                                                |
| **LLM**              | `quick_thinking_llm` + `bind_tools([get_news])`                                                                                           |
| **Prompt Location**  | `agents/prompts/social_media_analyst.md`                                                                                                  |
| **Responsibilities** | Analyze the sentiment trend in company-related social media and news, and produce a report with sentiment assessment and Markdown tables. |
| **Output**           | Writes to `state["sentiment_report"]`                                                                                                     |

#### News Analyst - News analyst

| Item                 | Content                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Definition File**  | `src/tradingagents/agents/analysts/news_analyst.py`                                                          |
| **Factory Function** | `create_news_analyst(llm: BaseChatModel)` (L10-52)                                                           |
| **LLM**              | `quick_thinking_llm` + `bind_tools([get_news, get_global_news])`                                             |
| **Prompt Location**  | `agents/prompts/news_analyst.md`                                                                             |
| **Responsibilities** | Analyze company news and global macro news, and produce a trading-oriented news report with Markdown tables. |
| **Output**           | Writes to `state["news_report"]`                                                                             |

#### Fundamentals Analyst - Fundamentals analyst

| Item                 | Content                                                                                                                                  |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `src/tradingagents/agents/analysts/fundamentals_analyst.py`                                                                              |
| **Factory Function** | `create_fundamentals_analyst(llm: BaseChatModel)` (L15-59)                                                                               |
| **LLM**              | `quick_thinking_llm` + `bind_tools([get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement])`                           |
| **Prompt Location**  | `agents/prompts/fundamentals_analyst.md`                                                                                                 |
| **Responsibilities** | Analyze financial statements, balance sheets, cash flows, and income statements, and produce a fundamentals report with Markdown tables. |
| **Output**           | Writes to `state["fundamentals_report"]`                                                                                                 |

#### Bull Researcher - Bullish researcher

| Item                 | Content                                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `src/tradingagents/agents/researchers/bull_researcher.py`                                                                             |
| **Factory Function** | `create_bull_researcher(llm: BaseChatModel, memory: FinancialSituationMemory)` (L9-63)                                                |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                                                                |
| **Prompt Location**  | `agents/prompts/bull_researcher.md`                                                                                                   |
| **Input**            | `market_report`, `sentiment_report`, `news_report`, `fundamentals_report`, debate history, previous bear argument, memory             |
| **Responsibilities** | Present bullish arguments focused on growth potential, competitive strengths, and positive indicators, while rebutting the bear view. |
| **Output**           | Updates `investment_debate_state`                                                                                                     |

#### Bear Researcher - Bearish researcher

| Item                 | Content                                                                                                                     |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `src/tradingagents/agents/researchers/bear_researcher.py`                                                                   |
| **Factory Function** | `create_bear_researcher(llm: BaseChatModel, memory: FinancialSituationMemory)` (L9-65)                                      |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                                                      |
| **Prompt Location**  | `agents/prompts/bear_researcher.md`                                                                                         |
| **Input**            | Same as Bull Researcher, but receives the previous bull argument                                                            |
| **Responsibilities** | Present bearish arguments focused on risks, competitive weaknesses, and negative indicators, while rebutting the bull view. |
| **Output**           | Updates `investment_debate_state`                                                                                           |

#### Research Manager - Investment judge

| Item                 | Content                                                                                      |
| -------------------- | -------------------------------------------------------------------------------------------- |
| **Definition File**  | `src/tradingagents/agents/managers/research_manager.py`                                      |
| **Factory Function** | `create_research_manager(llm: BaseChatModel, memory: FinancialSituationMemory)` (L9-62)      |
| **LLM**              | `deep_thinking_llm` (no tool binding)                                                        |
| **Prompt Location**  | `agents/prompts/research_manager.md`                                                         |
| **Input**            | Debate history and prior reflection memory                                                   |
| **Responsibilities** | Evaluate the Bull/Bear debate, decide Buy/Sell/Hold, and produce an investment plan.         |
| **Output**           | Writes to `state["investment_plan"]` and updates `investment_debate_state["judge_decision"]` |

#### Trader - Trader

| Item                 | Content                                                                                                                       |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `src/tradingagents/agents/trader/trader.py`                                                                                   |
| **Factory Function** | `create_trader(llm: BaseChatModel, memory: FinancialSituationMemory)` (L10-47)                                                |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                                                        |
| **Prompt Location**  | `agents/prompts/trader_system.md`, `agents/prompts/trader_user.md`                                                            |
| **Input**            | `investment_plan` and prior reflection memory                                                                                 |
| **Responsibilities** | Create a trading strategy based on the investment plan, and it must end with `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`. |
| **Output**           | Writes to `state["trader_investment_plan"]`                                                                                   |

#### Aggressive Debator - Aggressive risk debator

| Item                 | Content                                                                                                               |
| -------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `src/tradingagents/agents/risk_mgmt/aggressive_debator.py`                                                            |
| **Factory Function** | `create_aggressive_debator(llm: BaseChatModel)` (L7-57)                                                               |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                                                |
| **Prompt Location**  | `agents/prompts/aggressive_debator.md`                                                                                |
| **Input**            | `trader_investment_plan`, four analysis reports, debate history, and the latest Conservative/Neutral responses        |
| **Responsibilities** | Analyze from a high-risk high-reward perspective, emphasizing upside potential, growth, and innovation opportunities. |
| **Output**           | Updates `risk_debate_state`                                                                                           |

#### Conservative Debator - Conservative risk debator

| Item                 | Content                                                                                       |
| -------------------- | --------------------------------------------------------------------------------------------- |
| **Definition File**  | `src/tradingagents/agents/risk_mgmt/conservative_debator.py`                                  |
| **Factory Function** | `create_conservative_debator(llm: BaseChatModel)` (L7-56)                                     |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                        |
| **Prompt Location**  | `agents/prompts/conservative_debator.md`                                                      |
| **Input**            | Same as Aggressive Debator, but receives the latest Aggressive/Neutral responses              |
| **Responsibilities** | Analyze from an asset-protection perspective, emphasizing lower volatility and stable growth. |
| **Output**           | Updates `risk_debate_state`                                                                   |

#### Neutral Debator - Neutral risk debator

| Item                 | Content                                                                                |
| -------------------- | -------------------------------------------------------------------------------------- |
| **Definition File**  | `src/tradingagents/agents/risk_mgmt/neutral_debator.py`                                |
| **Factory Function** | `create_neutral_debator(llm: BaseChatModel)` (L7-58)                                   |
| **LLM**              | `quick_thinking_llm` (no tool binding)                                                 |
| **Prompt Location**  | `agents/prompts/neutral_debator.md`                                                    |
| **Input**            | Same as Aggressive Debator, but receives the latest Aggressive/Conservative responses  |
| **Responsibilities** | Balance risk and return while challenging both aggressive and conservative viewpoints. |
| **Output**           | Updates `risk_debate_state`                                                            |

#### Risk Manager - Risk judge

| Item                 | Content                                                                                                    |
| -------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Definition File**  | `src/tradingagents/agents/managers/risk_manager.py`                                                        |
| **Factory Function** | `create_risk_manager(llm: BaseChatModel, memory: FinancialSituationMemory)` (L9-69)                        |
| **LLM**              | `deep_thinking_llm` (no tool binding)                                                                      |
| **Prompt Location**  | `agents/prompts/risk_manager.md`                                                                           |
| **Input**            | Risk debate history and prior reflection memory                                                            |
| **Responsibilities** | Evaluate the three-sided risk debate, revise the trader's plan, and make the final Buy/Sell/Hold decision. |
| **Output**           | Writes to `state["final_trade_decision"]` and updates `risk_debate_state["judge_decision"]`                |

### 3.3 Prompt Management

All agent prompts are stored as Markdown template files under `src/tradingagents/agents/prompts/`. A `load_prompt(name)` helper (defined in `agents/prompts/__init__.py`) reads the file and returns the raw string, which callers can fill via `str.format()` or pass directly to `ChatPromptTemplate`.

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

### 3.4 Other Notes

- Only 4 **analysts** use tools (Function Calling); all other agents rely purely on LLM reasoning.
- **Bull/Bear/Trader/Research Manager/Risk Manager** use `FinancialSituationMemory` for memory retrieval.
- **Aggressive/Conservative/Neutral Debator** do not use memory.

---

## 4. Complete LangGraph Workflow

### 4.1 Core Files

| File                                           | Purpose                                                                                             |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `src/tradingagents/graph/trading_graph.py`     | Main `TradingAgentsGraph` class; initializes LLMs, memory, and `ToolNode`s, then compiles the graph |
| `src/tradingagents/graph/setup.py`             | `GraphSetup` class; defines all nodes and edges                                                     |
| `src/tradingagents/graph/conditional_logic.py` | `ConditionalLogic` class; defines conditional routing logic                                         |
| `src/tradingagents/graph/propagation.py`       | `Propagator` class; builds the initial state                                                        |
| `src/tradingagents/graph/reflection.py`        | `Reflector` class; performs post-trade reflection and memory updates                                |
| `src/tradingagents/graph/signal_processing.py` | `SignalProcessor` class; extracts BUY/SELL/HOLD from text                                           |

### 4.2 Graph Node List

Defined in the `setup_graph()` method in `src/tradingagents/graph/setup.py` (L109-200):

| Node Name                | Handler                                                           | Line | Description                 |
| ------------------------ | ----------------------------------------------------------------- | ---- | --------------------------- |
| `Market Analyst`         | `create_market_analyst(quick_thinking_llm)`                       | L144 | Market analysis             |
| `tools_market`           | `ToolNode([get_stock_data, get_indicators])`                      | L147 | Market tool execution       |
| `Msg Clear Market`       | `create_msg_delete()`                                             | L146 | Clear conversation history  |
| `Social Analyst`         | `create_social_media_analyst(quick_thinking_llm)`                 | L144 | Social analysis             |
| `tools_social`           | `ToolNode([get_news])`                                            | L147 | Social tool execution       |
| `Msg Clear Social`       | `create_msg_delete()`                                             | L146 | Clear conversation history  |
| `News Analyst`           | `create_news_analyst(quick_thinking_llm)`                         | L144 | News analysis               |
| `tools_news`             | `ToolNode([get_news, get_global_news, get_insider_transactions])` | L147 | News tool execution         |
| `Msg Clear News`         | `create_msg_delete()`                                             | L146 | Clear conversation history  |
| `Fundamentals Analyst`   | `create_fundamentals_analyst(quick_thinking_llm)`                 | L144 | Fundamentals analysis       |
| `tools_fundamentals`     | `ToolNode([get_fundamentals, ...])`                               | L147 | Fundamentals tool execution |
| `Msg Clear Fundamentals` | `create_msg_delete()`                                             | L146 | Clear conversation history  |
| `Bull Researcher`        | `create_bull_researcher(quick_thinking_llm, bull_memory)`         | L150 | Bullish debate              |
| `Bear Researcher`        | `create_bear_researcher(quick_thinking_llm, bear_memory)`         | L151 | Bearish debate              |
| `Research Manager`       | `create_research_manager(deep_thinking_llm, invest_judge_memory)` | L152 | Investment judge            |
| `Trader`                 | `create_trader(quick_thinking_llm, trader_memory)`                | L153 | Trading decision            |
| `Aggressive Analyst`     | `create_aggressive_debator(quick_thinking_llm)`                   | L154 | Aggressive risk analysis    |
| `Neutral Analyst`        | `create_neutral_debator(quick_thinking_llm)`                      | L155 | Neutral risk analysis       |
| `Conservative Analyst`   | `create_conservative_debator(quick_thinking_llm)`                 | L156 | Conservative risk analysis  |
| `Risk Judge`             | `create_risk_manager(deep_thinking_llm, risk_manager_memory)`     | L157 | Risk judge                  |

### 4.3 Edge Definitions

#### Fixed Edges (Unconditional)

| From                  | To                                                           | Location              |
| --------------------- | ------------------------------------------------------------ | --------------------- |
| `START`               | First analyst (default: `Market Analyst`)                    | `setup.py` L161       |
| `tools_{analyst}`     | `{Analyst} Analyst` (return to the same analyst to continue) | `setup.py` L101       |
| `Msg Clear {Analyst}` | Next analyst, or `Bull Researcher` if it is the last one     | `setup.py` L105, L107 |
| `Research Manager`    | `Trader`                                                     | `setup.py` L177       |
| `Trader`              | `Aggressive Analyst`                                         | `setup.py` L178       |
| `Risk Judge`          | `END`                                                        | `setup.py` L197       |

#### Conditional Edges - Defined in `conditional_logic.py`

**Analyst tool loop** (L14-44):

```
{Analyst} --> should_continue_{type}() --> tools_{type}      (if there are tool_calls)
                                       `--> Msg Clear {Type} (if there are no tool_calls, analysis is complete)
```

**Investment debate loop** (L46-54):

```
Bull Researcher --> should_continue_debate() --> Bear Researcher    (after Bull speaks)
                                              `--> Research Manager  (when max_debate_rounds is reached)

Bear Researcher --> should_continue_debate() --> Bull Researcher    (after Bear speaks)
                                              `--> Research Manager  (when max_debate_rounds is reached)
```

- Termination condition: `count >= 2 * max_debate_rounds` (default `max_debate_rounds = 1`, meaning one round each)

**Risk debate loop** (L56-66):

```
Aggressive   --> should_continue_risk_analysis() --> Conservative  (after Aggressive speaks)
                                                   `--> Risk Judge  (when max_risk_discuss_rounds is reached)

Conservative --> should_continue_risk_analysis() --> Neutral       (after Conservative speaks)
                                                   `--> Risk Judge  (when max_risk_discuss_rounds is reached)

Neutral      --> should_continue_risk_analysis() --> Aggressive    (after Neutral speaks)
                                                   `--> Risk Judge  (when max_risk_discuss_rounds is reached)
```

- Termination condition: `count >= 3 * max_risk_discuss_rounds` (default `max_risk_discuss_rounds = 1`, meaning one round each)
- Rotation order: Aggressive -> Conservative -> Neutral -> Aggressive -> ...

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

- **Main class:** `TradingAgentsGraph` (`src/tradingagents/graph/trading_graph.py`) — Pydantic `BaseModel` subclass. User-configurable fields use `Field()`, derived state (LLMs, memories, compiled graph) uses `@computed_field` + `@cached_property`.
- **Configuration:** Accepts a `TradingAgentsConfig` Pydantic model; side effects (`set_config`, `mkdir`) run in a `@model_validator(mode="after")` hook
- **Execution:** `propagate(company_name, trade_date)` - Builds the initial state and executes the graph
- **Reflection:** `reflect_and_remember(returns_losses)` - Performs post-trade reflection
- **Signal extraction:** `process_signal(full_signal)` - Extracts BUY/SELL/HOLD

---

## 5. Shared State Structure (State Schema)

Defined in `src/tradingagents/agents/utils/agent_states.py`.

### `AgentState` (L41-63) - Main state, inherits from `MessagesState`

| Field                     | Type                | Description                                           | Written By                                 |
| ------------------------- | ------------------- | ----------------------------------------------------- | ------------------------------------------ |
| `messages`                | `list[BaseMessage]` | Conversation history (inherited from `MessagesState`) | All agents                                 |
| `company_of_interest`     | `str`               | Company being traded                                  | Initialization                             |
| `trade_date`              | `str`               | Trading date                                          | Initialization                             |
| `sender`                  | `str`               | Name of the agent sending the message                 | All agents                                 |
| `market_report`           | `str`               | Market analysis report                                | Market Analyst                             |
| `sentiment_report`        | `str`               | Social sentiment report                               | Social Media Analyst                       |
| `news_report`             | `str`               | News analysis report                                  | News Analyst                               |
| `fundamentals_report`     | `str`               | Fundamentals report                                   | Fundamentals Analyst                       |
| `investment_debate_state` | `InvestDebateState` | Investment debate state                               | Bull/Bear/Research Manager                 |
| `investment_plan`         | `str`               | Investment plan                                       | Research Manager                           |
| `trader_investment_plan`  | `str`               | Trading plan                                          | Trader                                     |
| `risk_debate_state`       | `RiskDebateState`   | Risk debate state                                     | Aggressive/Conservative/Neutral/Risk Judge |
| `final_trade_decision`    | `str`               | Final trading decision                                | Risk Judge                                 |

### `InvestDebateState` (L8-14)

| Field              | Type  | Description             |
| ------------------ | ----- | ----------------------- |
| `bull_history`     | `str` | Bull debate history     |
| `bear_history`     | `str` | Bear debate history     |
| `history`          | `str` | Complete debate history |
| `current_response` | `str` | Latest response         |
| `judge_decision`   | `str` | Judge decision          |
| `count`            | `int` | Debate round counter    |

### `RiskDebateState` (L18-38)

| Field                           | Type  | Description                  |
| ------------------------------- | ----- | ---------------------------- |
| `aggressive_history`            | `str` | Aggressive debate history    |
| `conservative_history`          | `str` | Conservative debate history  |
| `neutral_history`               | `str` | Neutral debate history       |
| `history`                       | `str` | Complete debate history      |
| `latest_speaker`                | `str` | Most recent speaker          |
| `current_aggressive_response`   | `str` | Latest Aggressive response   |
| `current_conservative_response` | `str` | Latest Conservative response |
| `current_neutral_response`      | `str` | Latest Neutral response      |
| `judge_decision`                | `str` | Judge decision               |
| `count`                         | `int` | Debate round counter         |

---

## 6. Supporting Components (Memory / Reflection / Signal Processing)

### 6.1 FinancialSituationMemory - Memory system

- **File:** `src/tradingagents/agents/utils/memory.py` (L12-98)
- **Algorithm:** BM25Okapi (lexical similarity, no API required)
- **Storage:** Stores memory as `(situation, recommendation)` pairs
- **Retrieval:** `get_memories(current_situation, n_matches)` returns the most similar past experiences
- **There are 5 instances in total:** `bull_memory`, `bear_memory`, `trader_memory`, `invest_judge_memory`, `risk_manager_memory`

### 6.2 Reflector - Reflection system

- **File:** `src/tradingagents/graph/reflection.py` (L10-143)
- **Purpose:** Reflects on the quality of each agent's decision after the trade based on actual profit/loss, then updates the corresponding memory
- **Trigger:** After calling `TradingAgentsGraph.reflect_and_remember(returns_losses)`, reflection runs in this order:
    1. Bull Researcher (L76-87)
    2. Bear Researcher (L89-100)
    3. Trader (L102-113)
    4. Invest Judge (L115-128)
    5. Risk Manager (L130-143)

### 6.3 SignalProcessor - Signal extraction

- **File:** `src/tradingagents/graph/signal_processing.py` (L6-30)
- **Purpose:** Extracts BUY/SELL/HOLD from the Risk Judge's natural-language decision text
- **Method:** Uses an LLM for text extraction

---

## 7. LLM Configuration

### 7.1 Configuration Locations

- **Default config:** `src/tradingagents/default_config.py` — Pydantic models `TradingAgentsConfig` and `DataVendorsConfig`
- **LLM factory:** `src/tradingagents/llm_clients/factory.py` - `create_llm_client()` (L7-38)

### 7.2 LLM Tier Assignment

| Variable             | Config Key        | Default Model | Usage                                                                        |
| -------------------- | ----------------- | ------------- | ---------------------------------------------------------------------------- |
| `quick_thinking_llm` | `quick_think_llm` | `gpt-5-mini`  | All analysts, researchers, trader, debators, reflector, and signal processor |
| `deep_thinking_llm`  | `deep_think_llm`  | `gpt-5.2`     | Research Manager and Risk Manager                                            |

### 7.3 Supported LLM Providers

| Provider   | Config Value | Client Class                    |
| ---------- | ------------ | ------------------------------- |
| OpenAI     | `openai`     | `OpenAIClient`                  |
| Anthropic  | `anthropic`  | `AnthropicClient`               |
| Google     | `google`     | `GoogleClient`                  |
| xAI        | `xai`        | `OpenAIClient` (API-compatible) |
| Ollama     | `ollama`     | `OpenAIClient` (API-compatible) |
| OpenRouter | `openrouter` | `OpenAIClient` (API-compatible) |

---

## 8. Key Dependency List (To Be Removed)

The following LangGraph/LangChain related dependencies will need to be replaced or removed during the future refactor:

| Dependency               | Purpose                                                                              | Impact Scope                                               |
| ------------------------ | ------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| `langgraph`              | Graph construction, `StateGraph`, `ToolNode`, `CompiledStateGraph`                   | `graph/setup.py`, `graph/trading_graph.py`                 |
| `langchain_core`         | `BaseChatModel`, `@tool` decorator, `MessagesState`, `HumanMessage`, `RemoveMessage` | All agent definitions, `agent_states.py`, `agent_utils.py` |
| `langchain_openai`       | `ChatOpenAI` (used in a type hint in `signal_processing.py`)                         | `graph/signal_processing.py`                               |
| `langchain_anthropic`    | Anthropic LLM client                                                                 | `llm_clients/anthropic_client.py`                          |
| `langchain_google_genai` | Google LLM client                                                                    | `llm_clients/google_client.py`                             |

Core components that will need to be rebuilt during the refactor:

1. **Tool Calling mechanism** - Replaces the `@tool` decorator and `ToolNode`
2. **Graph / workflow engine** - Replaces `StateGraph` nodes, edges, and conditional branching
3. **State management** - Replaces `MessagesState` and `TypedDict` state passing
4. **LLM client abstraction** - Replaces the unified `BaseChatModel` interface (there is already some abstraction in `llm_clients/`)
