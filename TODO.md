# 系統架構與 Agents 盤點記錄

本文檔用於記錄目前 TradingAgents 的系統架構、資料獲取方式以及各 Agents 的職責與互動流程，以供後續其他 Agents 開發與重構參考。

## 1. 股市與外部資訊獲取方式

目前股市、新聞、財報等資訊是透過 **Function Calling (Tools)** 的方式提供給對應的 Analysts (分析師) Agents 使用。
所有工具的底層實作會透過 `src/tradingagents/dataflows/interface.py` 中的 `route_to_vendor` 路由到不同的資料供應商 (例如 `yfinance` 或 `alpha_vantage`)。

### 相關代碼位置

- **工具定義：** `src/tradingagents/agents/utils/`
    - `core_stock_tools.py`
    - `fundamental_data_tools.py`
    - `news_data_tools.py`
    - `technical_indicators_tools.py`
- **路由與供應商設定：** `src/tradingagents/dataflows/interface.py` 及 `src/tradingagents/dataflows/config.py`

### 目前可使用的工具清單

根據資料類別，目前提供以下工具給 Agents 使用：

1. **核心股市數據 (core_stock_apis)**
    - `get_stock_data`: 獲取指定股票的 OHLCV (開盤、最高、最低、收盤、成交量) 歷史價格數據。
2. **技術指標 (technical_indicators)**
    - `get_indicators`: 獲取指定股票的特定技術分析指標數據與報告。
3. **基本面數據 (fundamental_data)**
    - `get_fundamentals`: 獲取公司全面的基本面資料報告。
    - `get_balance_sheet`: 獲取資產負債表。
    - `get_cashflow`: 獲取現金流量表。
    - `get_income_statement`: 獲取損益表。
4. **新聞與內部交易數據 (news_data)**
    - `get_news`: 獲取特定公司的相關新聞。
    - `get_global_news`: 獲取全球總經市場新聞。
    - `get_insider_transactions`: 獲取公司內部人員的交易紀錄。

---

## 2. 目前存在的 Agents 與互動流程

系統的核心工作流使用 **LangGraph** 建構，定義於 `src/tradingagents/graph/setup.py` 與 `src/tradingagents/graph/trading_graph.py`。
整個流程可以分為四個主要階段：**資料收集與分析** -> **投資研究辯論** -> **交易決策** -> **風險控管辯論**。

### Agents 角色清單

- **分析師 (Analysts):** 負責使用 Tools 獲取資料並產生初步報告。
    - `Market Analyst`: 負責市場與價格分析 (使用 core_stock 與 technical 工具)。
    - `Social Media Analyst`: 負責社群媒體情緒分析。
    - `News Analyst`: 負責總經與公司新聞分析。
    - `Fundamentals Analyst`: 負責基本面與財報分析。
- **研究員與經理 (Researchers & Managers):** 負責根據分析師的報告進行多空辯論並得出結論。
    - `Bull Researcher`: 看多研究員。
    - `Bear Researcher`: 看空研究員。
    - `Research Manager` (Invest Judge): 研究經理 / 裁判，負責總結多空辯論。
- **交易員 (Trader):**
    - `Trader`: 根據研究經理的結論，制定初步的交易計畫與部位大小。
- **風險控管 (Risk Management):** 負責審查交易計畫的風險。
    - `Aggressive Analyst`: 激進型風險辯論者。
    - `Conservative Analyst`: 保守型風險辯論者。
    - `Neutral Analyst`: 中立型風險辯論者。
    - `Risk Judge` (Risk Manager): 風險經理 / 裁判，負責總結風險辯論並給出最終交易決策。

### 詳細互動流程 (Workflow)

整個圖形節點 (Graph) 依序執行如下：

1. **資料收集與分析階段 (Analysts Sequence)**
    - 工作流從選定的 Analysts 開始 (預設為 Market -> Social -> News -> Fundamentals)。
    - 每個 Analyst 會有一個迴圈：先判斷是否需要呼叫工具 (`tools_xxx` 節點)，獲取資料後回到 Analyst 進行分析。
    - 分析完成後，透過 `Msg Clear` 節點清理不必要的對話歷史，然後將狀態傳遞給下一個 Analyst。
2. **投資研究辯論階段 (Research Debate)**
    - 當所有 Analysts 都完成報告後，流程進入 `Bull Researcher`。
    - `Bull Researcher` 與 `Bear Researcher` 會根據現有報告進行多空辯論。
    - 透過條件邏輯 (`should_continue_debate`) 決定是否繼續辯論，或將辯論紀錄交由 `Research Manager`。
    - `Research Manager` 總結辯論並產出最終的「投資研究報告」。
3. **交易決策階段 (Trading)**
    - `Trader` 接收到投資研究報告後，會擬定初步的投資計畫 (Investment Plan)，包含買賣方向與建議數量。
4. **風險控管辯論階段 (Risk Analysis Debate)**
    - 初步投資計畫會送到風險控管團隊，由 `Aggressive Analyst` 開始。
    - `Aggressive Analyst`、`Conservative Analyst` 與 `Neutral Analyst` 針對該計畫的風險進行多方辯論。
    - 透過條件邏輯 (`should_continue_risk_analysis`) 決定是否繼續討論，或將討論結果交給 `Risk Judge` (Risk Manager)。
    - `Risk Judge` 考量所有風險意見後，做出最終的交易決策 (Final Trade Decision)。
    - 流程結束 (`END`)。

（備註：系統也實作了記憶機制 `FinancialSituationMemory`，透過 `Reflector` 元件在交易結束後根據損益進行反思與記憶更新。）
